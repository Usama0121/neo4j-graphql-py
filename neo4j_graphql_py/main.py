import re
import json
import logging
from pydash import filter_
from .selections import build_cypher_selection
from .utils import (is_mutation, is_add_relationship_mutation, type_identifiers, low_first_letter, cypher_directive,
                    mutation_meta_directive, extract_query_result, extract_selections,
                    fix_params_for_add_relationship_mutation)

logger = logging.getLogger('neo4j_graphql_py')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s:     %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


def neo4j_graphql(obj, context, resolve_info, debug=False, **kwargs):
    if is_mutation(resolve_info):
        query = cypher_mutation(context, resolve_info, **kwargs)
        if is_add_relationship_mutation(resolve_info):
            kwargs = fix_params_for_add_relationship_mutation(resolve_info, **kwargs)
        else:
            kwargs = {'params': kwargs}
    else:
        query = cypher_query(context, resolve_info, **kwargs)
    if debug:
        logger.info(query)
        logger.info(kwargs)

    with context.get('driver').session() as session:
        data = session.run(query, **kwargs)
        data = extract_query_result(data, resolve_info.return_type)
        return data


def cypher_query(context, resolve_info, first=-1, offset=0, _id=None, **kwargs):
    types_ident = type_identifiers(resolve_info.return_type)
    type_name = types_ident.get('type_name')
    variable_name = types_ident.get('variable_name')
    schema_type = resolve_info.schema.get_type(type_name)

    filtered_field_nodes = filter_(resolve_info.field_nodes, lambda n: n.name.value == resolve_info.field_name)

    # FIXME: how to handle multiple field_node matches
    selections = extract_selections(filtered_field_nodes[0].selection_set.selections, resolve_info.fragments)

    # if len(selections) == 0:
    #     # FIXME: why aren't the selections found in the filteredFieldNode?
    #     selections = extract_selections(resolve_info.operation.selection_set.selections, resolve_info.fragments)

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


def cypher_mutation(context, resolve_info, first=-1, offset=0, _id=None, **kwargs):
    # FIXME: lots of duplication here with cypherQuery, extract into util module
    types_ident = type_identifiers(resolve_info.return_type)
    type_name = types_ident.get('type_name')
    variable_name = types_ident.get('variable_name')
    schema_type = resolve_info.schema.get_type(type_name)

    filtered_field_nodes = filter_(resolve_info.field_nodes, lambda n: n.name.value == resolve_info.field_name)

    # FIXME: how to handle multiple field_node matches
    selections = extract_selections(filtered_field_nodes[0].selection_set.selections, resolve_info.fragments)

    # FIXME: support IN for multiple values -> WHERE
    arg_string = re.sub(r"\"([^(\")]+)\":", "\\1:", json.dumps(kwargs))

    id_where_predicate = f'WHERE ID({variable_name})={_id} ' if _id is not None else ''
    outer_skip_limit = f'SKIP {offset}{" LIMIT " + str(first) if first > -1 else ""}'

    cyp_dir = cypher_directive(resolve_info.schema.mutation_type, resolve_info.field_name)
    if cyp_dir:
        custom_cypher = cyp_dir.get('statement')
        query = (f'CALL apoc.cypher.doIt("{custom_cypher}", {arg_string}) YIELD value '
                 f'WITH apoc.map.values(value, [keys(value)[0]])[0] AS {variable_name} '
                 f'RETURN {variable_name} {{{build_cypher_selection("", selections, variable_name, schema_type, resolve_info)}}} '
                 f'AS {variable_name} {outer_skip_limit}')
    # No @cypher directive on MutationType
    elif resolve_info.field_name.startswith('create') or resolve_info.field_name.startswith('Create'):
        # Create node
        # TODO: handle for create relationship
        # TODO: update / delete
        # TODO: augment schema
        query = (f'CREATE ({variable_name}:{type_name}) SET {variable_name} = $params RETURN {variable_name} '
                 f'{{{build_cypher_selection("", selections, variable_name, schema_type, resolve_info)}}} '
                 f'AS {variable_name}')
    elif resolve_info.field_name.startswith('add') or resolve_info.field_name.startswith('Add'):
        mutation_meta = mutation_meta_directive(resolve_info.schema.mutation_type, resolve_info.field_name)
        relation_name = mutation_meta.get('relationship')
        from_type = mutation_meta.get('from')
        from_var = low_first_letter(from_type)
        to_type = mutation_meta.get('to')
        to_var = low_first_letter(to_type)
        from_param = resolve_info.schema.mutation_type.fields[resolve_info.field_name].ast_node.arguments[0].name.value[
                     len(from_var):]
        to_param = resolve_info.schema.mutation_type.fields[resolve_info.field_name].ast_node.arguments[1].name.value[
                   len(to_var):]
        query = (f'MATCH ({from_var}:{from_type} {{{from_param}: ${from_param}}}) '
                 f'MATCH ({to_var}:{to_type} {{{to_param}: ${to_param}}}) '
                 f'CREATE ({from_var})-[:{relation_name}]->({to_var}) '
                 f'RETURN {from_var} '
                 f'{{{build_cypher_selection("", selections, variable_name, schema_type, resolve_info)}}} '
                 f'AS {from_var}')
    else:
        raise Exception('Mutation does not follow naming conventions')
    return query


def augment_schema(schema):
    from .augment_schema import add_mutations_to_schema
    mutation_schema = add_mutations_to_schema(schema)
    return mutation_schema
