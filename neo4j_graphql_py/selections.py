from .utils import (cypher_directive_args, is_graphql_scalar_type, is_array_type, inner_type, cypher_directive,
                    relation_directive, inner_filter_params, compute_skip_limit)


def build_cypher_selection(initial, selections, variable_name, schema_type, resolve_info):
    if len(selections) == 0:
        return initial
    head_selection, *tail_selections = selections

    tail_params = {
        'selections': tail_selections,
        'variable_name': variable_name,
        'schema_type': schema_type,
        'resolve_info': resolve_info
    }

    field_name = head_selection.name.value
    comma_if_tail = ',' if len(tail_selections) > 0 else ''
    # Schema meta fields(__schema, __typename, etc)
    if not schema_type.fields.get(field_name):
        return build_cypher_selection(initial[1:initial.rfind(',')] if len(tail_selections) == 0 else initial,
                                      **tail_params)

    field_type = schema_type.fields[field_name].type

    inner_schema_type = inner_type(field_type)  # for target "field_type" aka label

    custom_cypher = cypher_directive(schema_type, field_name).get('statement')
    # Database meta fields(_id)
    if field_name == '_id':
        return build_cypher_selection(f'{initial}{field_name}: ID({variable_name}){comma_if_tail}', **tail_params)
    # Main control flow
    if is_graphql_scalar_type(inner_schema_type):
        if custom_cypher:
            return build_cypher_selection((f'{initial}{field_name}: apoc.cypher.runFirstColumnMany("{custom_cypher}", '
                                           f'{cypher_directive_args(variable_name, head_selection, schema_type, resolve_info)})'
                                           f'{comma_if_tail}'), **tail_params)

        # graphql scalar type, no custom cypher statement
        return build_cypher_selection(f'{initial} .{field_name} {comma_if_tail}', **tail_params)

    # We have a graphql object type
    nested_variable = variable_name + '_' + field_name
    skip_limit = compute_skip_limit(head_selection, resolve_info.variable_values)
    nested_params = {
        'initial': '',
        'selections': head_selection.selection_set.selections,
        'variable_name': nested_variable,
        'schema_type': inner_schema_type,
        'resolve_info': resolve_info
    }
    if custom_cypher:
        # similar: [ x IN apoc.cypher.runFirstColumnSingle("WITH {this} AS this MATCH (this)--(:Genre)--(o:Movie)
        # RETURN o", {this: movie}, true) |x {.title}][1..2])

        field_is_list = not not getattr(field_type, 'of_type', None)

        return build_cypher_selection(
            (f'{initial}{field_name}: {"" if field_is_list else "head("}'
             f'[ {nested_variable} IN apoc.cypher.runFirstColumnMany("{custom_cypher}", '
             f'{cypher_directive_args(variable_name, head_selection, schema_type, resolve_info)}) | {nested_variable} '
             f'{{{build_cypher_selection(**nested_params)}}}]'
             f'{"" if field_is_list else ")"}{skip_limit} {comma_if_tail}'), **tail_params)

    # graphql object type, no custom cypher

    rel = relation_directive(schema_type, field_name)
    rel_type = rel.get('name')
    rel_direction = rel.get('direction')
    subquery_args = inner_filter_params(head_selection)

    return build_cypher_selection(
        (f"{initial}{field_name}: {'head(' if not is_array_type(field_type) else ''}"
         f"[({variable_name}){'<' if rel_direction in ['in', 'IN'] else ''}"
         f"-[:{rel_type}]-{'>' if rel_direction in ['out', 'OUT'] else ''}"
         f"({nested_variable}:{inner_schema_type.name} {subquery_args}) | {nested_variable} "
         f"{{{build_cypher_selection(**nested_params)}}}]"
         f"{')' if not is_array_type(field_type) else ''}{skip_limit} {comma_if_tail}"), **tail_params)
