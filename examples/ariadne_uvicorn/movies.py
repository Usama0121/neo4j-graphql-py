import neo4j
import uvicorn
from ariadne.asgi import GraphQL
from neo4j_graphql_py import neo4j_graphql, make_executable_schema

typeDefs = '''
directive @cypher(statement: String!) on FIELD_DEFINITION
directive @relation(name:String!, direction:String!) on FIELD_DEFINITION
type Movie {
  title: String
  released: Int
  tagline: String
  similar(first: Int = 3, offset: Int = 0): [Movie] @cypher(statement: "WITH {this} AS this MATCH (o:Movie) WHERE this.released=o.released AND id(this)<>id(o) RETURN o")
  degree: Int @cypher(statement: "WITH {this} AS this RETURN SIZE((this)--())")
  actors(first: Int = 3, offset: Int = 0): [Person] @relation(name: "ACTED_IN", direction:"IN")
}

type Person {
    name: String
    born: Int
}

type Query {
  Movie(title: String, released: Int, tagline: String, first: Int, offset: Int): [Movie]
  MoviesByYear(year: Int): [Movie]
  Hello: String
}
'''

resolvers = {
    # root entry point to GraphQL service
    'Query': {
        'Movie': lambda obj, info, **kwargs: neo4j_graphql(obj, info.context, info, **kwargs),
        'MoviesByYear': lambda obj, info, **kwargs: neo4j_graphql(obj, info.context, info, **kwargs)
    }
}

schema = make_executable_schema(typeDefs, resolvers)

driver = None


def context(request):
    global driver
    if driver is None:
        driver = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j123"))

    return {'driver': driver, 'request': request}


rootValue = {}
app = GraphQL(schema=schema, root_value=rootValue, context_value=context, debug=True)
uvicorn.run(app)
