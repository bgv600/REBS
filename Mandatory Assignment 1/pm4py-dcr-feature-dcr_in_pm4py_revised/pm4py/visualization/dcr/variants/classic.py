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
            
            pending_record = ''
            if event in dcr.marking.pending:
                pending_record = '!'
            executed_record = ''
            if event in dcr.marking.executed:
                executed_record = '&#x2713;'
            label_map = ''
            if event in dcr.label_map:
                label_map = dcr.label_map[event]
            label = '{ ' + roles  + ' | ' + executed_record + ' ' + pending_record + ' } | { ' + label_map + ' }'
            included_style = 'solid'
            if event not in dcr.marking.included:
                included_style = 'dashed'
            viz.node(event, label, style=included_style, font_size=font_size)

    # Create nested clusters
    processed_groups = set()

    def add_to_cluster(group_name, parent_graph):
        if group_name in processed_groups:
            return
        processed_groups.add(group_name)
        
        with parent_graph.subgraph(name="cluster_"+group_name) as s:
            s.attr(label=group_name, style='rounded')
            
            # Add nodes and nested clusters to current cluster
            for member in dcr.nestedgroups[group_name]:
                if member in dcr.nestedgroups:
                    # Nested group, create a new cluster
                    add_to_cluster(member, s)
                else:
                    # Node, create same node
                    pending_record = ''
                    if member in dcr.marking.pending:
                        pending_record = '!'
                    executed_record = ''
                    if member in dcr.marking.executed:
                        executed_record = '&#x2713'
                    label_map = ''
                    if member in dcr.label_map:
                        label_map = dcr.label_map[member]
                    label = '{ ' + roles  + ' | ' + executed_record + ' ' + pending_record + ' } | { ' + label_map + ' }'
                    included_style = 'solid'
                    if member not in dcr.marking.included:
                        included_style = 'dashed'
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
                # Go inside cluster to look for nodes
                return find_head_or_tail(elem_s, 0)
            else:
                # # Go to next cluster of same depth
                return elem_s
                #i += 1
        else:
            print("node")
            return event

    # Add all relations, including those involving clusters
    for event in dcr.conditions:
        # If we have a group - set the edge to end there
        if event in dcr.nestedgroups:
            head = "cluster_"+event
            source = find_head_or_tail(event, 0)
        else:
            # Behave as normal
            head = None
            source = event
        for event_prime in dcr.conditions[event]:
            if event_prime in dcr.nestedgroups:
                # If we have a group - set edge to start from there
                tail = "cluster_"+event_prime
                target = find_head_or_tail(event_prime,0)
            else:
                # Behave as normal
                tail = None
                target = event_prime
            time = None
            if hasattr(dcr, 'timedconditions') and event in dcr.timedconditions and event_prime in dcr.timedconditions[event]:
                time = dcr.timedconditions[event][event_prime]
            create_edge(target, source, 'condition', viz, time, font_size, head=head, tail=tail)

    for event in dcr.responses:
        if event in dcr.nestedgroups:
            # If we have a group - set edge to start from there
            tail = "cluster_"+event
            target = find_head_or_tail(event, 0)
        else:
            tail = None
            target = event
        for event_prime in dcr.responses[event]:
            if event_prime in dcr.nestedgroups:
                # If we have a group - set the edge to end there
                head = "cluster_"+event_prime
                source = find_head_or_tail(event_prime, 0)
            else:
                head = None
                source = event_prime
            time = None
            if hasattr(dcr, 'timedconditions') and event in dcr.timedconditions and event_prime in dcr.timedconditions[event]:
                time = dcr.timedconditions[event][event_prime]
            create_edge(target, source, 'response', viz, time, font_size, head=head, tail=tail)


    for event in dcr.includes:
        if event in dcr.nestedgroups:
            tail = "cluster_"+event
            source = find_head_or_tail(event, 0)
        else:
            tail = None
            source = event
        for event_prime in dcr.includes[event]:
            if event_prime in dcr.nestedgroups:
                head = "cluster_"+event_prime
                target = find_head_or_tail(event_prime, 0)    
            else:
                head = None
                target = event_prime
            create_edge(source, target, 'include', viz, tail=tail, head=head)

    for event in dcr.excludes:
        if event in dcr.nestedgroups:
            tail = "cluster_"+event
            source = find_head_or_tail(event, 0)
        else:
            tail = None
            source = event
        for event_prime in dcr.excludes[event]:
            if event_prime in dcr.nestedgroups:
                head = "cluster_"+event_prime
                target = find_head_or_tail(event_prime, 0)
            else:
                head = None
                target = event_prime
            create_edge(source, target, 'exclude', viz, tail=tail, head=head)


    if hasattr(dcr, 'noresponses'):
        for event in dcr.noresponses:
            if event in dcr.nestedgroups:
                tail = "cluster_"+event
                source = find_head_or_tail(event, 0)
            else:
                tail = None
                source = event
            for event_prime in dcr.noresponses[event]:
                if event_prime in dcr.nestedgroups:
                    head = "cluster_"+event
                    target = find_head_or_tail(event_prime, 0)
                else:
                    head = None
                    target = event_prime
                create_edge(event, event_prime, 'noresponse', viz)

    if hasattr(dcr, 'milestones'):
        for event in dcr.milestones:
            if event in dcr.nestedgroups:
                tail = "cluster_"+event
                source = find_head_or_tail(event, 0)
            else:
                tail = None
                source = event
            for event_prime in dcr.milestones[event]:
                if event_prime in dcr.nestedgroups:
                    head = "cluster_"+event_prime
                    target = find_head_or_tail(event_prime, 0)
                else:
                    head = None
                    target = event_prime
                create_edge(source, target, 'milestone', viz)

    viz.attr(overlap='false')
    viz.format = image_format.replace("html", "plain-text")

    return viz
