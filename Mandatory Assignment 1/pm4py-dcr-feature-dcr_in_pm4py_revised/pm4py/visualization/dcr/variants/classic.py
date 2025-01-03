import tempfile
from enum import Enum

from click import option
from graphviz import Digraph

from pm4py.objects.dcr.timed.obj import TimedDcrGraph
from pm4py.objects.dcr.utils.utils import time_to_iso_string
from pm4py.util import exec_utils, constants

filename = tempfile.NamedTemporaryFile(suffix=".gv")
filename.close()

class Parameters(Enum):
    FORMAT = "format"
    RANKDIR = "set_rankdir"
    AGGREGATION_MEASURE = "aggregationMeasure"
    FONT_SIZE = "font_size"
    BGCOLOR = "bgcolor"
    DECORATIONS = "decorations"

# Extended create_edge input to also include a head and tail for connecting to or from clusters
def create_edge(source, target, relation, viz, time = None, font_size = None,time_precision='D', head = None, tail = None):
    viz.edge_attr['labeldistance'] = '0.0'
    if font_size:
        font_size = int(font_size)
        font_size = str(int(font_size - 2/3*font_size))
    if time:
        time = time_to_iso_string(time, time_precision)
        match time_precision:
            case 'D':
                time = None if time=='P0D' else time
            case 'H':
                time = None if time=='P0DT0H' else time
            case 'M':
                time = None if time=='P0DT0H0M' else time
            case 'S':
                time = None if time=='P0DT0H0M0S' else time

    print(f"source: {source}")
    print(f"target: {target}")

    match relation:
        case 'condition':
            if time:
                viz.edge(source, target, color='#FFA500', arrowhead='dotnormal', label=time, labelfontsize=font_size, lhead=head, ltail=tail) 
            else:
                viz.edge(source, target, color='#FFA500', arrowhead='dotnormal', lhead=head, ltail=tail)
        case 'exclude':
            viz.edge(source, target, color='#FC0C1B', arrowhead='normal', arrowtail='none', headlabel='%', labelfontcolor='#FC0C1B', labelfontsize='8', ltail=tail, lhead=head)
        case 'include':
            viz.edge(source, target, color='#30A627', arrowhead='normal', arrowtail='none', headlabel='+', labelfontcolor='#30A627', labelfontsize='10', ltail=tail, lhead=head)
        case 'response':
            if time:
                viz.edge(source, target, color='#2993FC', arrowhead='normal', arrowtail='dot', dir='both', label=time, labelfontsize=font_size, lhead=head, ltail=tail)
            else:
                viz.edge(source, target, color='#2993FC', arrowhead='normal', arrowtail='dot', dir='both', lhead=head, ltail=tail)
        case 'noresponse':
            viz.edge(source, target, color='#7A514D', arrowhead='normal', headlabel='x', labelfontcolor='#7A514D', labelfontsize='8', arrowtail='dot', dir='both', ltail=tail, lhead=head)
        case 'milestone':
            viz.edge(source, target, color='#A932D0', arrowhead='normal', headlabel='&#9671;', labelfontcolor='#A932D0', labelfontsize='8', arrowtail='dot', dir='both', ltail=tail, lhead=head)
    return



def apply(dcr: TimedDcrGraph, parameters, head=None, tail=None):
    if parameters is None:
        parameters = {}

    image_format = exec_utils.get_param_value(Parameters.FORMAT, parameters, "png")
    set_rankdir = exec_utils.get_param_value(Parameters.RANKDIR, parameters, 'LR')
    font_size = exec_utils.get_param_value(Parameters.FONT_SIZE, parameters, "12")
    bgcolor = exec_utils.get_param_value(Parameters.BGCOLOR, parameters, constants.DEFAULT_BGCOLOR)

    viz = Digraph("", filename=filename.name, engine='dot', graph_attr={'bgcolor': bgcolor, 'rankdir': set_rankdir,
                                                                        'compound': 'true'},
                  node_attr={'shape': 'Mrecord'}, edge_attr={'arrowsize': '0.5'})

    # Create regular nodes first
    for event in dcr.events:
        #if event not in dcr.nestedgroups_map:
        if event not in dcr.nestedgroups:
            label = None
            try:
                roles = []
                key_list = list(dcr.role_assignments.keys())
                value_list = list(dcr.role_assignments.values())
                for count, value in enumerate(value_list):
                    if event in value:
                        roles.append(key_list[count])
                roles = ', '.join(roles)
            except AttributeError:
                roles = ''
            
            pending_record = '!' if event in dcr.marking.pending else ''
            executed_record = '&#x2713;' if event in dcr.marking.executed else ''
            label_map = dcr.label_map[event] if event in dcr.label_map else ''
            label = '{ ' + roles + ' | ' + executed_record + ' ' + pending_record + ' } | { ' + label_map + ' }'
            
            included_style = 'solid' if event in dcr.marking.included else 'dashed'
            viz.node(event, label, style=included_style, font_size=font_size)

    # Create nested clusters
    processed_groups = set()

    def add_to_cluster(group_name, parent_graph):
        print(1)
        if group_name in processed_groups:
            return
        processed_groups.add(group_name)
        
        #with parent_graph.subgraph(name='cluster_' + group_name) as s:
        with parent_graph.subgraph(name="cluster_"+group_name) as s:
            s.attr(label=group_name, style='rounded')
            
            # Add nodes and nested clusters to this cluster
            for member in dcr.nestedgroups[group_name]:
                if member in dcr.nestedgroups:
                    # Nested group, create a new cluster
                    add_to_cluster(member, s)
                else:
                    # This is a regular node, add it to current cluster
                    pending_record = '!' if member in dcr.marking.pending else ''
                    executed_record = '&#x2713;' if member in dcr.marking.executed else ''
                    label_map = dcr.label_map[member] if member in dcr.label_map else ''
                    label = '{ | ' + executed_record + ' ' + pending_record + ' } | { ' + label_map + ' }'
                    included_style = 'solid' if member in dcr.marking.included else 'dashed'
                    s.node(member, label, style=included_style, font_size=font_size)

    # Create all clusters starting from top-level groups
    for group in dcr.nestedgroups:
        if group not in processed_groups:
            add_to_cluster(group, viz)

    def find_head_or_tail(event, i):
        if event in dcr.nestedgroups:
            grouplist = list(dcr.nestedgroups[event])
            elem_s = grouplist[i]
            if elem_s in dcr.nestedgroups:
                return find_head_or_tail(elem_s, i+1)
            else:
                return elem_s
        else:
            return event

    # Add all relations, including those involving clusters
    for event in dcr.conditions:
        head = "cluster_"+event
        source = find_head_or_tail(event, 0)
        for event_prime in dcr.conditions[event]:
            time = None
            tail = "cluster_"+event_prime
            target = find_head_or_tail(event_prime,0)
            if hasattr(dcr, 'timedconditions') and event in dcr.timedconditions and event_prime in dcr.timedconditions[event]:
                time = dcr.timedconditions[event][event_prime]
            create_edge(target, source, 'condition', viz, time, font_size, head=head, tail=tail)

    for event in dcr.responses:
        tail = "cluster_"+event
        print(f"Tail: {tail}")
        source = find_head_or_tail(event, 0)
        for event_prime in dcr.responses[event]:
            time = None
            head = "cluster_"+event_prime
            print(f"Head: {head}")
            target = find_head_or_tail(event_prime, 0)
            if hasattr(dcr, 'timedconditions') and event in dcr.timedconditions and event_prime in dcr.timedconditions[event]:
                time = dcr.timedconditions[event][event_prime]
            create_edge(source, target, 'response', viz, time, font_size, head=head, tail=tail)


    for event in dcr.includes:
        tail = "cluster_"+event
        source = find_head_or_tail(event, 0)
        for event_prime in dcr.includes[event]:
            head = "cluster_"+event_prime
            target = find_head_or_tail(event_prime, 0)    
            create_edge(source, target, 'include', viz, tail=tail, head=head)

    for event in dcr.excludes:
        print(f"Event: {event}")
        print(f"groups map: {list[dcr.nestedgroups.keys()]}")
        if event in list[dcr.nestedgroups.keys()]:
            tail = "cluster_"+event
        else:
            tail = None
        print(f"Tail: {tail}")
        source = find_head_or_tail(event, 0)
        print(f"Source: {source}")
        for event_prime in dcr.excludes[event]:
            print(f"Event prime: {event_prime}")
            head = "cluster_"+event_prime
            target = find_head_or_tail(event_prime, 0)
            print(f"Target: {target}")
            create_edge(source, target, 'exclude', viz, tail=tail, head=head)

    if hasattr(dcr, 'noresponses'):
        for event in dcr.noresponses:
            tail = "cluster_"+event
            source = find_head_or_tail(event, 0)
            for event_prime in dcr.noresponses[event]:
                head = "cluster_"+event
                target = find_head_or_tail(event_prime, 0)
                create_edge(event, event_prime, 'noresponse', viz)

    if hasattr(dcr, 'milestones'):
        for event in dcr.milestones:
            tail = "cluster_"+event
            source = find_head_or_tail(event, 0)
            for event_prime in dcr.milestones[event]:
                head = "cluster_"+event_prime
                target = find_head_or_tail(event_prime, 0)
                create_edge(source, target, 'milestone', viz)

    viz.attr(overlap='false')
    viz.format = image_format.replace("html", "plain-text")

    return viz
