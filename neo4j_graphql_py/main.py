import re
import json
import logging
import pydash as _
from .utils import cypher_directive_args

RETURN_TYPE_ENUM = {
    'OBJECT': 0,
    'ARRAY': 1
}
logger = logging.getLogger('neo4j_graphql_py')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s:     %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


def neo4j_graphql(obj, context, resolve_info, **kwargs):
    field_type = str(inner_type(resolve_info.return_type))
    variable = field_type[0].lower() + field_type[1:]
    query = cypher_query(context, resolve_info, **kwargs)
    logger.info(query)
    return_type = (RETURN_TYPE_ENUM['ARRAY']
                   if str(resolve_info.return_type).startswith("[")
                   else RETURN_TYPE_ENUM['OBJECT'])

    def fun(result):
        result = [record.get(variable) for record in result.data()]
        if return_type == RETURN_TYPE_ENUM['ARRAY']:
            return result
        elif return_type == RETURN_TYPE_ENUM['OBJECT']:
            if len(result) > 0:
                return result[0]
            else:
                return None

    with context.get('driver').session() as session:
        data = session.run(query, **kwargs)
        data = fun(data)
        return data


def cypher_query(context, resolve_info, **kwargs):
    page_params = {
        "first": None if kwargs.get('first') is None else str(kwargs.pop('first')),
        "offset": '0' if kwargs.get('offset') is None else str(kwargs.pop('offset'))
    }

    field_type = str(inner_type(resolve_info.return_type))
    variable = field_type[0].lower() + field_type[1:]
    schema_type = resolve_info.schema.get_type(field_type)

    filtered_field_nodes = _.filter_(resolve_info.field_nodes, lambda x: x.name.value == resolve_info.field_name)

    # FIXME: how to handle multiple field_node matches

    selections = filtered_field_nodes[0].selection_set.selections
    where_predicate = ''
    if '_id' in kwargs:
        where_predicate = f' WHERE ID({variable})={kwargs.pop("_id")}'

    # FIXME: support IN for multiple values -> WHERE
    arg_string = re.sub(r"\"([^(\")]+)\":", "\\1:", json.dumps(kwargs))

    query = f'MATCH ({variable}:{field_type} {arg_string}){where_predicate}'
    query += f' RETURN {variable} {{' + build_cypher_selection('', selections, variable, schema_type, resolve_info)

    query += f'}} AS {variable}'
    query += (f' SKIP {page_params["offset"]}'
              f'{" LIMIT " + page_params["first"] if page_params["first"] is not None else ""}')

    return query


def build_cypher_selection(initial, selections, variable, schema_type, resolve_info):
    # FIXME: resolve_info not needed

    if len(selections) == 0:
        return initial
    (head_selection, tail_selections) = selections[0], selections[1:]

    field_name = head_selection.name.value
    if not schema_type.fields.get(field_name):
        return build_cypher_selection(initial[1:initial.rfind(',')] if len(tail_selections) == 0 else initial,
                                      tail_selections, variable, schema_type, resolve_info)

    field_type = schema_type.fields[field_name].type

    inner = inner_type(field_type)  # for target "field_type" aka label

    field_has_cypher_directive = len([directive for directive in schema_type.fields[field_name].ast_node.directives if
                                      directive.name.value == 'cypher']) > 0

    if field_has_cypher_directive:

        statement = _.find(_.find(schema_type.fields[field_name].ast_node.directives,
                                  lambda directive: directive.name.value == 'cypher').arguments,
                           lambda argument: argument.name.value == 'statement').value.value
        if type(inner).__name__ == "GraphQLScalarType":
            return build_cypher_selection((initial +
                                           f'{field_name}: apoc.cypher.runFirstColumn("{statement}", '
                                           f'{cypher_directive_args(variable, head_selection, schema_type)}, false)'
                                           f'{"," if len(tail_selections) > 0 else ""}'),
                                          tail_selections, variable, schema_type, resolve_info)
        else:
            # similar: [ x IN apoc.cypher.runFirstColumn("WITH {this} AS this MATCH (this)--(:Genre)--(o:Movie)
            # RETURN o", {this: movie}, true) |x {.title}][1..2])

            nested_variable = variable + '_' + field_name
            skip_limit = compute_skip_limit(head_selection)
            field_is_list = not not getattr(field_type, 'of_type', None)

            return build_cypher_selection(
                (initial +
                 f'{field_name}: {"" if field_is_list else "head("}'
                 f'[ x IN apoc.cypher.runFirstColumn("{statement}", '
                 f'{cypher_directive_args(variable, head_selection, schema_type)}, true) | x '
                 f'{{{build_cypher_selection("", head_selection.selection_set.selections, nested_variable, inner, resolve_info)}}}]'
                 f'{"" if field_is_list else ")"}{skip_limit} '
                 f'{"," if len(tail_selections) > 0 else ""}'),
                tail_selections, variable, schema_type, resolve_info)

    elif type(inner_type(field_type)).__name__ == "GraphQLScalarType":
        return build_cypher_selection(initial + f' .{field_name} {"," if len(tail_selections) > 0 else ""}',
                                      tail_selections, variable, schema_type, resolve_info)
    else:
        # field is an obj
        nested_variable = variable + '_' + field_name
        skip_limit = compute_skip_limit(head_selection)
        relation_directive = _.find(schema_type.fields[field_name].ast_node.directives,
                                    lambda directive: directive.name.value == 'relation')

        rel_type = _.find(relation_directive.arguments, lambda argument: argument.name.value == 'name').value.value
        rel_direction = _.find(relation_directive.arguments,
                               lambda argument: argument.name.value == 'direction').value.value

        return_type = RETURN_TYPE_ENUM['ARRAY'] if str(field_type).startswith("[") else RETURN_TYPE_ENUM['OBJECT']

        return build_cypher_selection(
            (initial +
             f"{field_name}: {'head(' if return_type == RETURN_TYPE_ENUM['OBJECT'] else ''}"
             f"[({variable}){'<' if rel_direction == 'in' or rel_direction == 'IN' else ''}"
             f"-[:{rel_type}]-{'>' if rel_direction == 'out' or rel_direction == 'OUT' else ''}"
             f"({nested_variable}:{inner.name}) | {nested_variable} "
             f"{{{build_cypher_selection('', head_selection.selection_set.selections, nested_variable, inner, resolve_info)}}}]"
             f"{')' if return_type == RETURN_TYPE_ENUM['OBJECT'] else ''}{skip_limit} "
             f"{',' if len(tail_selections) > 0 else ''}"),
            tail_selections, variable, schema_type, resolve_info)


def inner_type(field_type):
    return inner_type(field_type.of_type) if getattr(field_type, 'of_type', None) else field_type


def argument_value(selection, name):
    arg = _.find(selection.arguments, lambda argument: argument.name.value == name)
    return None if arg is None else arg.value.value


def compute_skip_limit(selection):
    first = argument_value(selection, "first")
    offset = argument_value(selection, "offset")
    if first is None and offset is None:
        return ""
    if offset is None:
        return f'[..{first}]'
    if first is None:
        return f'[{offset}..]'
    return f'[{offset}..{int(offset) + int(first)}]'
