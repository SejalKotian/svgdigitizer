from svg.path import parse_path
from svgpathtools import Path, Line
from xml.dom import minidom
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from functools import cached_property

import re

ref_point_regex_str = r'^(?P<point>(x|y)\d)\: ?(?P<value>-?\d+\.?\d*) ?(?P<unit>.+)?'
scale_bar_regex_str = r'^(?P<axis>x|y)(_scale_bar|sb)\: ?(?P<value>-?\d+\.?\d*) ?(?P<unit>.+)?'
scaling_factor_regex_str = r'^(?P<axis>x|y)(_scaling_factor|sf)\: (?P<value>-?\d+\.?\d*)'

class SvgData:
    def __init__(self, filename, xlabel=None, ylabel=None, sampling_interval=None):
        '''filename: should be a valid svg file created according to the documentation'''
        self.filename = filename

        self.xlabel = xlabel or 'x'
        self.ylabel = ylabel or 'y'

        self.doc = minidom.parse(self.filename)

        self.ref_points, self.real_points = self.get_points()
        
        self.trafo = {}
        for axis in ['x','y']:
            self.trafo[axis] = self.get_trafo(axis)

        self.sampling_interval = sampling_interval

        self.get_parsed()
        self.create_df()
    
    @cached_property
    def transformed_sampling_interval(self):
        factor = 1/((self.trafo['x'](self.sampling_interval)-self.trafo['x'](0))/(self.sampling_interval/1000))
        return factor
    
    def get_points(self):
        '''Creates:
        ref_points: relative values of the spheres/eclipses in the svg file.
        real_points: real values of the points given in the title text of the svg file.'''
        ref_points = {}
        real_points = {}


        for text in self.doc.getElementsByTagName('text'):

            # parse text content

            text_content = text.firstChild.firstChild.data
            regex_match = re.match(ref_point_regex_str, text_content)
            if regex_match:
                ref_point_id = regex_match.group("point")
                real_points[ref_point_id] = float(regex_match.group("value"))
           
                x_text = float(text.firstChild.getAttribute('x'))
                y_text = float(text.firstChild.getAttribute('y'))
                # get path which is grouped with text
                group = text.parentNode

                parsed_path = parse_path(group.getElementsByTagName("path")[0].getAttribute('d'))

                # always take the point of the path which is further away from text origin
                path_points = []
                path_points.append((parsed_path.point(0).real, parsed_path.point(0).imag))
                path_points.append((parsed_path.point(1).real, parsed_path.point(1).imag))
                if (((path_points[0][0]-x_text)**2 + (path_points[0][1]-y_text)**2)**0.5 > 
                ((path_points[1][0]-x_text)**2 + (path_points[1][1]-y_text)**2)**0.5):
                    point = 0
                else:
                    point = 1
            
                ref_points[ref_point_id] = {'x': path_points[point][0], 'y': path_points[point][1]}

        
        print('Ref points: ', ref_points)
        print('point values: ',real_points)
        return ref_points, real_points
        
    @cached_property
    def scale_bars(self):
        scale_bars = {}

        for text in self.doc.getElementsByTagName('text'):
            # parse text content

            text_content = text.firstChild.firstChild.data
            regex_match = re.match(scale_bar_regex_str, text_content)
            if regex_match:
                x_text = float(text.firstChild.getAttribute('x'))
                y_text = float(text.firstChild.getAttribute('y'))
                # get paths which are grouped with text
                group = text.parentNode.parentNode
                paths = group.getElementsByTagName("path")
                end_points = []
                for path in paths:
                    parsed_path = parse_path(path.getAttribute('d'))
                # always take the point of the path which is further away from text origin
                    path_points = []
                    path_points.append((parsed_path.point(0).real, parsed_path.point(0).imag))
                    path_points.append((parsed_path.point(1).real, parsed_path.point(1).imag))
                    if (((path_points[0][0]-x_text)**2 + (path_points[0][1]-y_text)**2)**0.5 > 
                    ((path_points[1][0]-x_text)**2 + (path_points[1][1]-y_text)**2)**0.5):
                        point = 0
                    else:
                        point = 1
                    end_points.append(path_points[point])
                
                scale_bars[regex_match.group("axis")] = {}
                if regex_match.group("axis") == 'x':
                    scale_bars[regex_match.group("axis")]['ref'] = abs(end_points[1][0] - end_points[0][0] )
                elif regex_match.group("axis") == 'y':
                    scale_bars[regex_match.group("axis")]['ref'] = abs(end_points[1][1] - end_points[0][1])
                scale_bars[regex_match.group("axis")]['real'] = float(regex_match.group("value"))

        return scale_bars

    @cached_property
    def scaling_factors(self):
        scaling_factors = {'x': 1, 'y': 1}
        for text in self.doc.getElementsByTagName('text'):

            # parse text content
            text_content = text.firstChild.firstChild.data
            regex_match = re.match(scaling_factor_regex_str, text_content)

            if regex_match:
                scaling_factors[regex_match.group("axis")] = float(regex_match.group("value"))
        return scaling_factors

    def get_parsed(self):
        '''cuve function'''
        self.allresults = {}
        for pathid, pvals in self.paths.items():
            self.allresults[pathid] = self.get_real_values(pvals)
    

    def get_trafo(self, axis):
        # we assume a rectangular plot
        # value = mref * (path - refpath0 ) + refvalue0
        #print('refpath ', refpath, 'refvalues ', refvalues)
        p_real = self.real_points
        p_ref = self.ref_points
        try:
            mref = (p_real[f'{axis}2'] - p_real[f'{axis}1']) / (p_ref[f'{axis}2'][axis] - p_ref[f'{axis}1'][axis]) / self.scaling_factors[axis]
            trafo = lambda pathdata: mref * (pathdata - p_ref[f'{axis}1'][axis]) + p_real[f'{axis}1']
        except KeyError:
            mref = -1/self.scale_bars[axis]['ref'] * self.scale_bars[axis]['real']  / self.scaling_factors[axis] # unclear why we need negative sign: now I know, position of origin !!
            trafo = lambda pathdata: mref * (pathdata - p_ref[f'{axis}1'][axis]) + p_real[f'{axis}1']
        return trafo
    
    def get_real_values(self, xpathdata):
        xnorm = self.trafo['x'](xpathdata[:, 0])
        ynorm = self.trafo['y'](xpathdata[:, 1])
        return np.array([xnorm, ynorm])

    @cached_property
    def paths(self):
        r"""
        Return the paths that are tracing plots in the SVG, i.e., return all
        the `<path>` tags that are not used for other purposes such as pointing
        to axis labels.
        """
        return {
            path.getAttribute('id'): self.parse_pathstring(path.getAttribute('d'))
            for path in self.doc.getElementsByTagName("path")
            # Only take paths into account which are not in groups since those are
            # the paths pointing to labels on the axes.
            if path.parentNode.nodeName != 'g' or
                # This is complicated by the fact that layers as created by inkscape
                # are also groups. Such layers have the 'inkscape:groupmode' set.
                path.parentNode.getAttribute("inkscape:groupmode") == 'layer' or
                # But this attribute goes away when exporting to plain SVG. In
                # such case, we recover layers as the groups that contain more
                # than one path.
                len(path.parentNode.getElementsByTagName("path")) > 1
        }
    
    
    def parse_pathstring(self, path_string):
        path = parse_path(path_string)
        posxy = []
        for e in path:
            x0 = e.start.real
            y0 = e.start.imag
            x1 = e.end.real
            y1 = e.end.imag
            posxy.append([x0, y0])

        return np.array(posxy)


    def sample_path(self, path_string):
        '''samples a path with equidistant x segment by segment'''
        path = Path(path_string)
        xmin, xmax, ymin, ymax = path.bbox()
        x_samples = np.linspace(xmin, xmax, int(abs(xmin - xmax)/self.transformed_sampling_interval))
        points = []
        for segment in path:
            segment_path = Path(segment)
            xmin_segment, xmax_segment, _, _ = segment.bbox()
            segment_points = [[],[]]

            for x in x_samples:
                # only sample the x within the segment
                if x >= xmin_segment and x <= xmax_segment:
                    intersects = Path(Line(complex(x,ymin),complex(x,ymax))).intersect(segment_path)
                    # it is possible that a segment includes both scan directions
                    # which leads to two intersections
                    for i in range(len(intersects)):
                        point = intersects[i][0][1].point(intersects[i][0][0])
                        segment_points[i].append((point.real, point.imag))   

            # second intersection is appended in reverse order!! 
            if len(segment_points[1]) > 0:    
                segment_points[0].extend(segment_points[1][::-1]) 
            # sometimes segments are shorter than sampling interval   
            if len(segment_points[0]) > 0:    
                first_segment_point = (segment.point(0).real, segment.point(0).imag)    

                if (((segment_points[0][-1][0]-first_segment_point[0])**2+(segment_points[0][-1][1]-first_segment_point[1])**2)**0.5 >    
                    ((segment_points[0][0][0]-first_segment_point[0])**2+(segment_points[0][0][1]-first_segment_point[1])**2)**0.5):    
                    points.extend(segment_points[0])    
                else:     
                    points.extend(segment_points[0][::-1]) 

        return np.array(points)  

    def create_df(self):
        data = [self.allresults[list(self.allresults)[idx]].transpose() for idx, i in enumerate(self.allresults)]
        self.dfs = [pd.DataFrame(data[idx],columns=[self.xlabel,self.ylabel]) for idx, i in enumerate(data)]

        #for df in self.dfs:
        #    df['t'] = self.create_time_axis(df)
            #df = df[['t','U','I']].copy() #reorder columns does not work
    
    def plot(self):
        '''curve function'''
        #resdict = self.allresults
        #for i, v in resdict.items():
        #    plt.plot(v[0], v[1], label=i)
            
        fig, ax = plt.subplots(1,1)
        for i, df in enumerate(self.dfs):
            df.plot(x=self.xlabel, y=self.ylabel, ax=ax, label=f'curve {i}') 
        # do we want the path in the legend as it was in the previous version?
        #plt.legend()
        plt.xlabel(self.xlabel)
        plt.ylabel(self.ylabel)
        plt.tight_layout()
        plt.show()
    