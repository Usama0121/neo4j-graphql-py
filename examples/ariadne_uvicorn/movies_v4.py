import uvicorn
from neo4j import GraphDatabase
from ariadne.asgi import GraphQL
from neo4j_graphql_py import neo4j_graphql
from ariadne import QueryType, make_executable_schema, MutationType, gql

typeDefs = gql('''
directive @cypher(statement: String!) on FIELD_DEFINITION
directive @relation(name:String!, direction:String!) on FIELD_DEFINITION
type Movie {
  _id: ID
  movieId: ID!
  title: String
  tagline: String
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
  _id: ID!
  name: String
  movies(first: Int = 3, offset: Int = 0): [Movie] @relation(name: "IN_GENRE", direction: "IN")
  highestRatedMovie: Movie @cypher(statement: "MATCH (m:Movie)-[:IN_GENRE]->(this) RETURN m ORDER BY m.imdbRating DESC LIMIT 1")
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
enum BookGenre {
  Mystery,
  Science,
  Math
}
type Book {
  title: String!  
  genre: BookGenre
}
type Query {
  Movie(id: ID, title: String, year: Int, plot: String, poster: String, imdbRating: Float, first: Int, offset: Int): [Movie]
  MoviesByYear(year: Int): [Movie]
  AllMovies: [Movie]
  MovieById(movieId: ID!): Movie
  GenresBySubstring(substring: String): [Genre] @cypher(statement: "MATCH (g:Genre) WHERE toLower(g.name) CONTAINS toLower($substring) RETURN g")
  Books: [Book]
  Actors: [Actor]
}
type Mutation {
  CreateGenre(name: String): Genre @cypher(statement: "CREATE (g:Genre) SET g.name = $name RETURN g")
  CreateMovie(movieId: ID!, title: String, year: Int, plot: String, poster: String, imdbRating: Float): Movie
  CreateBook(title: String!,genre: BookGenre): Book @cypher(statement: "CREATE (b:Book) SET b.title = $title, b.genre = $genre RETURN b")
}
'''
               )

query = QueryType()
mutation = MutationType()

# @mutation.field('AddMovieGenre')
@query.field('Actors')
@query.field('Movie')
@query.field('MoviesByYear')
@query.field('AllMovies')
@query.field('MovieById')
@query.field('GenresBySubstring')
@query.field('Books')
@mutation.field('CreateGenre')
@mutation.field('CreateMovie')
@mutation.field('CreateBook')
async def resolve(obj, info, **kwargs):
    return await neo4j_graphql(obj, info.context, info, True, **kwargs)


schema = make_executable_schema(typeDefs, query, mutation)

driver = None


def context(request):
    global driver
    if driver is None:
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "Whoami!9070"))

    return {'driver': driver, 'request': request}


root_value = {}
app = GraphQL(schema=schema, root_value=root_value, context_value=context, debug=True)
uvicorn.run(app)
driver.close()

