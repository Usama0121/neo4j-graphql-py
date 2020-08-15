from .main import neo4j_graphql
from graphql import print_schema
from pydash import filter_, reduce_
from .utils import inner_type, make_executable_schema, low_first_letter


def add_mutations_to_schema(schema):
    types = types_to_augment(schema)

    # FIXME: don't use printSchema (custom directives are lost), instead use extend schema
    # FIXME: type extensions are lost
    mutation_schema_sdl = print_schema(schema)

    # TODO: compose augment funcs
    # let mutationSchemaSDLWithTypes = augmentTypes(types, schema, mutationSchemaSDL);

    mutation_schema_sdl_with_types_and_mutations = augment_mutations(types, schema, mutation_schema_sdl)

    def resolve_neo4j(obj, info, **kwargs):
        return neo4j_graphql(obj, info.context, info, **kwargs)

    # console.log(mutationSchemaSDLWithTypesAndMutations);
    def f(acc, t):
        # FIXME: inspect actual mutations, not construct mutation names here
        acc['Mutation'][f'Create{t}'] = resolve_neo4j
        for field_type in types:
            for rel_mutation in add_relationship_mutations(schema.type_map[field_type], True):
                acc['Mutation'][rel_mutation] = resolve_neo4j
        return acc

    resolvers = reduce_(types, f, {'Query': {}, 'Mutation': {}})

    # delegate query resolvers to original schema
    def f2(acc, t):
        acc['Query'][t] = resolve_neo4j
        return acc

    resolvers = reduce_(list(schema.query_type.fields.keys()), f2, resolvers)

    mutation_schema = make_executable_schema(mutation_schema_sdl_with_types_and_mutations, resolvers)

    final_schema = mutation_schema
    return final_schema


def types_to_augment(schema):
    """
     * Given a GraphQLSchema return an array of the type names,
     * excluding Query and Mutation types
     * @param {GraphQLSchema} schema
     * @returns {string[]}
    """
    # TODO: check for @ignore and @model directives
    return filter_(list(schema.type_map.keys()),
                   lambda t: False if schema.type_map[t].ast_node is None
                   else schema.type_map[
                            t].ast_node.kind == 'object_type_definition' and t != 'Query' and t != 'Mutation')


def augment_types(types, schema, sdl):
    """
    #  * Generate type extensions for each type:
    #  *   - add _id field
    #  * @param {string[]} types
    #  * @param schema
    #  * @param {string} sdl
    #  * @returns {string} SDL type extensions
    """
    return reduce_(types,
                   lambda acc, t: acc + '' if t in ['Mutation', 'Query']
                   else acc + f'extend type {t} {{ _id:ID }}', sdl)


def augment_mutations(types, schema, sdl):
    # FIXME: requires placeholder Query type
    return (sdl +
            f'''
            extend schema {{
              mutation: Mutation
            }}
        
        
            type Mutation {{
                {reduce_(types, lambda acc, t: acc + f'{create_mutation(schema.type_map[t])} '
                                                     f'{add_relationship_mutations(schema.type_map[t])} ', '')}
            }}
            '''
            )


def create_mutation(field_type):
    return f'Create{field_type.name}({param_signature(field_type)}): {field_type.name}'


def add_relationship_mutations(field_type, names_only=False):
    mutations = ''
    mutation_names = []

    def f1(field):
        i = 0
        while i < len(field.ast_node.directives):
            return field.ast_node.directives[i].name.value == 'relation'

    relationship_fields = filter_(field_type.fields, f1)

    for field in relationship_fields:
        relation_directive = (
            filter_(field.ast_node.directives, lambda d: d.name.value == 'relation')[0])
        rel_type = filter_(relation_directive.arguments, lambda a: a.name.value == 'name')[0]
        rel_direction = filter_(relation_directive.arguments, lambda a: a.name.value == 'direction')[0]

        if rel_direction.value.value in ['out', 'OUT']:
            from_type = field_type
            to_type = inner_type(field.type)
        else:
            from_type = inner_type(field.type)
            to_type = field_type
        from_pk = primary_key(from_type)
        to_pk = primary_key(to_type)

        # FIXME: could add relationship properties here
        mutations += (f'Add{from_type.name}{to_type.name}'
                      f'({low_first_letter(from_type.name + from_pk.ast_node.name.value)}: {inner_type(from_pk.type).name}!, '
                      f'{low_first_letter(to_type.name + to_pk.ast_node.name.value)}: {inner_type(to_pk.type).name}!): '
                      f'{from_type.name} @MutationMeta(relationship: "{rel_type.value.value}", from: "{from_type.name}", to: "{to_type.name}")')
        mutation_names.append(f'Add{from_type.name}{to_type.name}')
    if names_only:
        return mutation_names
    else:
        return mutations


def primary_key(field_type):
    """
     * Returns the field to be treated as the "primary key" for this type
     * Primary key is determined as the first of:
     *   - non-null ID field
     *   - ID field
     *   - first String field
     *   - first field
     *
     * @param {object_type_definition} type
     * @returns {FieldDefinition} primary key field
    """
    # Find the primary key for the type
    # first field with a required ID
    # if no required ID type then first required type
    pk = first_non_null_and_id_field(field_type)
    if not pk:
        pk = first_id_field(field_type)
    if not pk:
        pk = first_non_null_field(field_type)
    if not pk:
        pk = first_field(field_type)

    return pk


def param_signature(field_type):
    def fun(acc, f):
        if f == '_id' or (getattr(inner_type(field_type.fields[f].type), 'ast_node', None) is not None and inner_type(
                field_type.fields[f].type).ast_node.kind == 'object_type_definition'):
            # TODO: exclude @cypher fields
            # TODO: exclude object types?
            return acc + ''
        else:
            return acc + f' {f}: {inner_type(field_type.fields[f].type).name}, '

    return reduce_(list(field_type.fields.keys()), fun, '')


def first_non_null_and_id_field(field_type):
    fields = filter_(list(field_type.fields.keys()),
                     lambda t: type(field_type.fields[t]).__name__ == 'GraphQLNonNull'
                               and field_type.fields[t].type.name == 'ID')
    if len(fields) > 0:
        return field_type.fields[fields[0]]
    else:
        return None


def first_id_field(field_type):
    fields = filter_(list(field_type.fields.keys()), lambda t: inner_type(field_type.fields[t].type).name == 'ID')
    if len(fields) > 0:
        return field_type.fields[fields[0]]
    else:
        return None


def first_non_null_field(field_type):
    fields = filter_(list(field_type.fields.keys()), lambda t: type(field_type.fields[t]).__name__ == 'GraphQLNonNull')
    if len(fields) > 0:
        return field_type.fields[fields[0]]
    else:
        return None


def first_field(field_type):
    return field_type.fields[list(field_type.fields.keys())[0]]
