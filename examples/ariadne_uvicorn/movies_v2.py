import uvicorn
from neo4j import GraphDatabase
from ariadne.asgi import GraphQL
from neo4j_graphql_py import neo4j_graphql
from ariadne import QueryType, make_executable_schema

typeDefs = '''
directive @cypher(statement: String!) on FIELD_DEFINITION
directive @relation(name:String!, direction:String!) on FIELD_DEFINITION
type Movie {
  movieId: ID!
  title: String
  year: Int
  plot: String
  poster: String
  imdbRating: Float
  genres: [Genre] @relation(name: "IN_GENRE", direction: "OUT")
  similar(first: Int = 3, offset: Int = 0, limit: Int = 5): [Movie] @cypher(statement: "WITH {this} AS this MATCH (this)--(:Genre)--(o:Movie) RETURN o LIMIT {limit}")
  mostSimilar: Movie @cypher(statement: "WITH {this} AS this RETURN this")
  degree: Int @cypher(statement: "WITH {this} AS this RETURN SIZE((this)--())")
  actors(first: Int = 3, offset: Int = 0): [Actor] @relation(name: "ACTED_IN", direction:"IN")
  avgStars: Float
  filmedIn: State @relation(name: "FILMED_IN", direction: "OUT")
  scaleRating(scale: Int = 3): Float @cypher(statement: "WITH $this AS this RETURN $scale * this.imdbRating")
  scaleRatingFloat(scale: Float = 1.5): Float @cypher(statement: "WITH $this AS this RETURN $scale * this.imdbRating")
}

type Genre {
  name: String
}

type State {
  name: String
}

interface Person {
  id: ID!
  name: String
}

type Actor {
  id: ID!
  name: String
  movies: [Movie] @relation(name: "ACTED_IN", direction: "OUT")
}

type User implements Person {
  id: ID!
  name: String
}


type Query {
  Movie(id: ID, title: String, year: Int, plot: String, poster: String, imdbRating: Float, first: Int, offset: Int): [Movie]
  MoviesByYear(year: Int): [Movie]
  AllMovies: [Movie]
  MovieById(movieId: ID!): Movie
}
'''
query = QueryType()


@query.field('Movie')
@query.field('MoviesByYear')
@query.field('AllMovies')
@query.field('MovieById')
def resolve(obj, info, **kwargs):
    return neo4j_graphql(obj, info.context, info, **kwargs)


schema = make_executable_schema(typeDefs, query)

driver = None


def context(request):
    global driver
    if driver is None:
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j123"))

    return {'driver': driver, 'request': request}


rootValue = {}
app = GraphQL(schema=schema, root_value=rootValue, context_value=context, debug=True)
uvicorn.run(app)
