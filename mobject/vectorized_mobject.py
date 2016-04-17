import re

from .mobject import Mobject

from helpers import *

class VMobject(Mobject):
    CONFIG = {
        "fill_color"       : BLACK,
        "fill_opacity"     : 0.0,
        #Indicates that it will not be displayed, but
        #that it should count in parent mobject's path
        "is_subpath"       : False,
        "close_new_points" : True,
        "mark_paths_closed" : False,
    }
    def __init__(self, *args, **kwargs):
        self.subpath_mobjects = []
        Mobject.__init__(self, *args, **kwargs)

    ## Colors
    def init_colors(self):
        self.set_stroke(self.color, self.stroke_width)
        self.set_fill(self.fill_color, self.fill_opacity)
        return self

    def set_family_attr(self, attr, value):
        for mob in self.submobject_family():
            setattr(mob, attr, value)

    def set_fill(self, color = None, opacity = 1.0):
        if color is not None:
            self.set_family_attr("fill_rgb", color_to_rgb(color))
        self.set_family_attr("fill_opacity", opacity)
        return self

    def set_stroke(self, color = None, width = None):
        if color is not None:
            self.set_family_attr("stroke_rgb", color_to_rgb(color))
        if width is not None:
            self.set_family_attr("stroke_width", width)
        return self

    def highlight(self, color):
        self.set_fill(color = color)
        self.set_stroke(color = color)
        return self

    def get_fill_color(self):
        return Color(rgb = self.fill_rgb)

    def get_fill_opacity(self):
        return self.fill_opacity

    def get_stroke_color(self):
        return Color(rgb = self.stroke_rgb)

    #TODO, get color?  Specify if stroke or fill
    #is the predominant color attribute?

    ## Drawing
    def start_at(self, point):
        if len(self.points) == 0:
            self.points = np.zeros((1, 3))
        self.points[0] = point
        return self

    def add_control_points(self, control_points):
        assert(len(control_points) % 3 == 0)
        self.points = np.append(
            self.points,
            control_points,
            axis = 0
        )
        return self

    def is_closed(self):
        return is_closed(self.points)

    def set_anchors_and_handles(self, anchors, handles1, handles2):
        assert(len(anchors) == len(handles1)+1)
        assert(len(anchors) == len(handles2)+1)
        total_len = 3*(len(anchors)-1) + 1
        self.points = np.zeros((total_len, self.dim))
        self.points[0] = anchors[0]
        arrays = [handles1, handles2, anchors[1:]]
        for index, array in enumerate(arrays):
            self.points[index+1::3] = array
        return self.points

    def set_points_as_corners(self, points):
        if len(points) <= 1:
            return self
        points = np.array(points)
        self.set_anchors_and_handles(points, *[
            interpolate(points[:-1], points[1:], alpha)
            for alpha in 1./3, 2./3
        ])
        return self

    def set_points_smoothly(self, points):
        if len(points) <= 1:
            return self
        h1, h2 = get_smooth_handle_points(points)
        self.set_anchors_and_handles(points, h1, h2)
        return self

    def set_points(self, points):
        self.points = np.array(points)
        return self

    def set_anchor_points(self, points, mode = "smooth"):
        if not isinstance(points, np.ndarray):
            points = np.array(points)
        if self.close_new_points and not is_closed(points):
            points = np.append(points, [points[0]], axis = 0)
        if mode == "smooth":
            self.set_points_smoothly(points)
        elif mode == "corners":
            self.set_points_as_corners(points)
        else:
            raise Exception("Unknown mode")
        return self

    def change_mode(self, mode):
        anchors, h1, h2 = self.get_anchors_and_handles()
        self.set_anchor_points(anchors, mode = mode)
        return self

    def make_smooth(self):
        return self.change_mode("smooth")

    def make_jagged(self):
        return self.change_mode("corners")

    def add_subpath(self, points):
        """
        A VMobject is meant to represnt
        a single "path", in the svg sense of the word.
        However, one such path may really consit of separate
        continuous components if there is a move_to command.

        These other portions of the path will be treated as submobjects,
        but will be tracked in a separate special list for when
        it comes time to display.
        """
        subpath_mobject = VMobject(
            is_subpath = True
        )
        subpath_mobject.set_points(points)
        self.subpath_mobjects.append(subpath_mobject)
        self.add(subpath_mobject)
        return self

    ## Information about line

    def component_curves(self):
        for n in range(self.get_num_anchor_points()-1):
            yield self.get_nth_curve(n)

    def get_nth_curve(self, n):
        return bezier(self.points[3*n:3*n+4])

    def get_num_anchor_points(self):
        return (len(self.points) - 1)/3 + 1

    def point_from_proportion(self, alpha):
        num_cubics = self.get_num_anchor_points()-1
        interpoint_alpha = num_cubics*(alpha % (1./num_cubics))
        index = 3*int(alpha*num_cubics)
        cubic = bezier(self.points[index:index+4])
        return cubic(interpoint_alpha)

    def get_anchors_and_handles(self):
        return [
            self.points[i::3]
            for i in range(3)
        ]

    ## Alignment

    def align_points_with_larger(self, larger_mobject):
        assert(isinstance(larger_mobject, VMobject))
        num_anchors = self.get_num_anchor_points()
        if num_anchors <= 1:
            point = self.points[0] if len(self.points) else np.zeros(3)
            self.points = np.zeros(larger_mobject.points.shape)
            self.points[:,:] = point
            return self
        points = np.array([self.points[0]])
        target_len = larger_mobject.get_num_anchor_points()-1
        num_curves = self.get_num_anchor_points()-1
        #Curves in self are buckets, and we need to know 
        #how many new anchor points to put into each one.  
        #Each element of index_allocation is like a bucket, 
        #and its value tells you the appropriate index of 
        #the smaller curve.
        index_allocation = (np.arange(target_len) * num_curves)/target_len
        for index in range(num_curves):
            curr_bezier_points = self.points[3*index:3*index+4]
            num_inter_curves = sum(index_allocation == index)
            step = 1./num_inter_curves
            alphas = np.arange(0, 1+step, step)
            for a, b in zip(alphas, alphas[1:]):
                new_points = partial_bezier_points(curr_bezier_points, a, b)
                points = np.append(
                    points, new_points[1:], axis = 0
                )
        self.set_points(points)
        return self

    def get_point_mobject(self, center = None):
        if center is None:
            center = self.get_center()
        return VectorizedPoint(center)

    def interpolate_color(self, mobject1, mobject2, alpha):
        attrs = [
            "stroke_rgb", 
            "stroke_width",            
            "fill_rgb", 
            "fill_opacity",
        ]
        for attr in attrs:
            setattr(self, attr, interpolate(
                getattr(mobject1, attr),
                getattr(mobject2, attr),
                alpha
            ))

    def become_partial(self, mobject, a, b):
        assert(isinstance(mobject, VMobject))        
        #Partial curve includes three portions:
        #-A middle section, which matches the curve exactly
        #-A start, which is some ending portion of an inner cubic
        #-An end, which is the starting portion of a later inner cubic
        if a <= 0 and b >= 1:
            self.set_points(mobject.points)
            return self
        num_cubics = mobject.get_num_anchor_points()-1
        lower_index = int(a*num_cubics)
        upper_index = int(b*num_cubics)
        points = np.array(
            mobject.points[3*lower_index:3*upper_index+4]
        )
        if len(points) > 1:
            a_residue = (num_cubics*a)%1
            b_residue = (num_cubics*b)%1
            points[:4] = partial_bezier_points(
                points[:4], a_residue, 1
            )
            points[-4:] = partial_bezier_points(
                points[-4:], 0, b_residue
            )
        self.set_points(points)
        return self


class VectorizedPoint(VMobject):
    CONFIG = {
        "color" : BLACK,
    }
    def __init__(self, location = ORIGIN, **kwargs):
        VMobject.__init__(self, **kwargs)
        self.set_points([location])






