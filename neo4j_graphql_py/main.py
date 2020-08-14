import re
import json
import logging
from pydash import filter_, find
from .utils import cypher_directive_args

logger = logging.getLogger('neo4j_graphql_py')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s:     %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


async def neo4j_graphql(obj, context, resolve_info, debug=False, **kwargs):
    query = cypher_query(context, resolve_info, **kwargs)
    if debug:
        logger.info(query)

    with context.get('driver').session() as session:
        data = await session.run(query, **kwargs)
        data = extract_query_result(data, resolve_info.return_type)
        return data


def cypher_query(context, resolve_info, first=-1, offset=0, _id=None, **kwargs):
    types_ident = type_identifiers(resolve_info.return_type)
    type_name = types_ident.get('type_name')
    variable_name = types_ident.get('variable_name')
    schema_type = resolve_info.schema.get_type(type_name)

    filtered_field_nodes = filter_(resolve_info.field_nodes, lambda n: n.name.value == resolve_info.field_name)

    # FIXME: how to handle multiple field_node matches

    selections = filtered_field_nodes[0].selection_set.selections

    # FIXME: support IN for multiple values -> WHERE
    arg_string = re.sub(r"\"([^(\")]+)\":", "\\1:", json.dumps(kwargs))

    id_where_predicate = f'WHERE ID({variable_name})={_id} ' if _id is not None else ''
    outer_skip_limit = f'SKIP {offset}{" LIMIT " + str(first) if first > -1 else ""}'

    cyp_dir = cypher_directive(resolve_info.schema.query_type, resolve_info.field_name)
    if cyp_dir:
        custom_cypher = cyp_dir.get('statement')
        query = (f'WITH apoc.cypher.runFirstColumn("{custom_cypher}", {arg_string}, true) AS x '
                 f'UNWIND x AS {variable_name} RETURN {variable_name} '
                 f'{{{build_cypher_selection("", selections, variable_name, schema_type, resolve_info)}}} '
                 f'AS {variable_name} {outer_skip_limit}')
    else:
        # No @cypher directive on QueryType
        query = f'MATCH ({variable_name}:{type_name} {arg_string}) {id_where_predicate}'
        query += (f'RETURN {variable_name} '
                  f'{{{build_cypher_selection("", selections, variable_name, schema_type, resolve_info)}}}'
                  f' AS {variable_name} {outer_skip_limit}')

    return query


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
    if not schema_type.fields.get(field_name):
        # meta field type
        return build_cypher_selection(initial[1:initial.rfind(',')] if len(tail_selections) == 0 else initial,
                                      **tail_params)
    comma_if_tail = ',' if len(tail_selections) > 0 else ''

    field_type = schema_type.fields[field_name].type

    inner_schema_type = inner_type(field_type)  # for target "field_type" aka label

    custom_cypher = cypher_directive(schema_type, field_name).get('statement')

    if is_graphql_scalar_type(inner_schema_type):
        if custom_cypher:
            return build_cypher_selection((f'{initial}{field_name}: apoc.cypher.runFirstColumn("{custom_cypher}", '
                                           f'{cypher_directive_args(variable_name, head_selection, schema_type, resolve_info)}, false)'
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
        # similar: [ x IN apoc.cypher.runFirstColumn("WITH {this} AS this MATCH (this)--(:Genre)--(o:Movie)
        # RETURN o", {this: movie}, true) |x {.title}][1..2])

        field_is_list = not not getattr(field_type, 'of_type', None)

        return build_cypher_selection(
            (f'{initial}{field_name}: {"" if field_is_list else "head("}'
             f'[ {nested_variable} IN apoc.cypher.runFirstColumn("{custom_cypher}", '
             f'{cypher_directive_args(variable_name, head_selection, schema_type, resolve_info)}, true) | {nested_variable} '
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


def type_identifiers(return_type):
    type_name = str(inner_type(return_type))
    return {'variable_name': low_first_letter(type_name),
            'type_name': type_name}


def is_graphql_scalar_type(field_type):
    return type(field_type).__name__ == 'GraphQLScalarType'


def is_array_type(field_type):
    return str(field_type).startswith('[')


def low_first_letter(word):
    return word[0].lower() + word[1:]


def inner_type(field_type):
    return inner_type(field_type.of_type) if getattr(field_type, 'of_type', None) else field_type


def directive_with_args(directive_name, *args):
    def fun(schema_type, field_name):
        def field_directive(schema_type, field_name, directive_name):
            return find(schema_type.fields[field_name].ast_node.directives, lambda d: d.name.value == directive_name)

        def directive_argument(directive, name):
            return find(directive.arguments, lambda a: a.name.value == name).value.value

        directive = field_directive(schema_type, field_name, directive_name)
        ret = {}
        if directive:
            ret.update({key: directive_argument(directive, key) for key in args})
        return ret

    return fun


cypher_directive = directive_with_args('cypher', 'statement')
relation_directive = directive_with_args('relation', 'name', 'direction')


def inner_filter_params(selections):
    query_params = {}
    if len(selections.arguments) > 0:
        query_params = {arg.name.value: arg.value.value for arg in selections.arguments if
                        arg.name.value not in ['first', 'offset']}
    # FIXME: support IN for multiple values -> WHERE
    query_params = re.sub(r"\"([^(\")]+)\":", "\\1:", json.dumps(query_params))

    return query_params


def argument_value(selection, name, variable_values):
    arg = find(selection.arguments, lambda argument: argument.name.value == name)
    return (
        None if arg is None
        else variable_values[name] if getattr(arg.value, 'value', None) is None
                                      and name in variable_values and arg.value.kind == 'variable'
        else arg.value.value
    )


def extract_query_result(records, return_type):
    type_ident = type_identifiers(return_type)
    variable_name = type_ident.get('variable_name')
    result = [record.get(variable_name) for record in records.data()]
    return result if is_array_type(return_type) else result[0] if len(result) > 0 else None


def compute_skip_limit(selection, variable_values):
    first = argument_value(selection, "first", variable_values)
    offset = argument_value(selection, "offset", variable_values)
    if first is None and offset is None:
        return ""
    if offset is None:
        return f'[..{first}]'
    if first is None:
        return f'[{offset}..]'
    return f'[{offset}..{int(offset) + int(first)}]'
