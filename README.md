# neo4j-graphql-py

A GraphQL to Cypher query execution layer for Neo4j and Python GraphQL implementations.

## Installation and usage

Install

```
pip install neo4j-graphql-py
```


Then call `neo4j_graphql()` in your GraphQL resolver. Your GraphQL query will be translated to Cypher and the query passed to Neo4j.

~~~python
from neo4j_graphql_py import neo4j_graphql

def resolve(obj, info, **kwargs):
    return neo4j_graphql(obj, info.context, info, **kwargs)

resolvers = {
  'Query': {
    'Movie':resolve
  }
}
~~~

## What is `neo4j-graphql-py`

A package to make it easier to use GraphQL and [Neo4j](https://neo4j.com/) together. `neo4j-graphql-py` translates GraphQL queries to a single [Cypher](https://neo4j.com/developer/cypher/) query, eliminating the need to write queries in GraphQL resolvers and for batching queries. It also exposes the Cypher query language through GraphQL via the `@cypher` schema directive.

## How it works

### Start with a GraphQL schema

GraphQL First Development is all about starting with a well defined GraphQL schema. Here we'll use the GraphQL schema IDL syntax:

~~~python
type_defs = '''
directive @cypher(statement: String!) on FIELD_DEFINITION
directive @relation(name:String!, direction:String!) on FIELD_DEFINITION

type Movie {
  movieId: ID!
  title: String
  year: Int
  plot: String
  poster: String
  imdbRating: Float
  similar(first: Int = 3, offset: Int = 0): [Movie] @cypher(statement: "MATCH (this)-[:IN_GENRE]->(:Genre)<-[:IN_GENRE]-(o:Movie) RETURN o")
  degree: Int @cypher(statement: "RETURN SIZE((this)-->())")
  actors(first: Int = 3, offset: Int = 0): [Actor] @relation(name: "ACTED_IN", direction:"IN")
}

type Actor {
  id: ID!
  name: String
  movies: [Movie]
}


type Query {
  Movie(id: ID, title: String, year: Int, imdbRating: Float, first: Int, offset: Int): [Movie]
}
'''
~~~

We define two types, `Movie` and `Actor` as well as a top level Query `Movie` which becomes our entry point. This looks like a standard GraphQL schema, except for the use of two directives `@relation` and `@cypher`. In GraphQL directives allow us to annotate fields and provide an extension point for GraphQL.

* `@cypher` directive - maps the specified Cypher query to the value of the field. In the Cypher query, `this` is bound to the current object being resolved.
* `@relation` directive - used to indicate relationships in the data model. The `name` argument specifies the relationship type, and `direction` indicates the direction of the relationship ("IN" or "OUT" are valid values)



### Translate GraphQL To Cypher

Inside each resolver, use `neo4j-graphql()` to generate the Cypher required to resolve the GraphQL query, passing through the query arguments, context and resolveInfo objects.

~~~python
from neo4j_graphql_py import neo4j_graphql

resolvers = {
  # entry point to GraphQL service
  'Query': {
    'Movie': lambda obj, info, **kwargs: neo4j_graphql(obj, info.context,info, **kwargs)
  }
}
~~~

GraphQL to Cypher translation works by inspecting the GraphQL schema, the GraphQL query and arguments. For example, this simple GraphQL query

~~~graphql
{
  Movie(title: "River Runs Through It, A") {
    title
    year
    imdbRating
  }
}
~~~

is translated into the Cypher query

~~~cypher
MATCH (movie:Movie {title: "River Runs Through It, A"})
RETURN movie { .title , .year , .imdbRating } AS movie
SKIP 0
~~~

A slightly more complicated traversal

~~~graphql
{
  Movie(title: "River Runs Through It, A") {
    title
    year
    imdbRating
    actors {
      name
    }
  }
}
~~~

becomes

~~~cypher
MATCH (movie:Movie {title: "River Runs Through It, A"})
RETURN movie { .title , .year , .imdbRating, actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor) | movie_actors { .name }] }
AS movie
SKIP 0
~~~

## `@cypher` directive

**NOTE: The `@cypher` directive has a dependency on the APOC procedure library, specifically the function `apoc.cypher.runFirstColumn` to run sub-queries. If you'd like to make use of the `@cypher` feature you'll need to install [appropriate version of APOC](https://github.com/neo4j-contrib/neo4j-apoc-procedures) in Neo4j**

GraphQL is fairly limited when it comes to expressing complex queries such as filtering, or aggregations. We expose the graph querying language Cypher through GraphQL via the `@cypher` directive. Annotate a field in your schema with the `@cypher` directive to map the results of that query to the annotated GraphQL field. For example:

~~~graphql
type Movie {
  movieId: ID!
  title: String
  year: Int
  plot: String
  similar(first: Int = 3, offset: Int = 0): [Movie] @cypher(statement: "MATCH (this)-[:IN_GENRE]->(:Genre)<-[:IN_GENRE]-(o:Movie) RETURN o ORDER BY COUNT(*) DESC")
}
~~~

The field `similar` will be resolved using the Cypher query

~~~cypher
MATCH (this)-[:IN_GENRE]->(:Genre)<-[:IN_GENRE]-(o:Movie) RETURN o ORDER BY COUNT(*) DESC
~~~

to find movies with overlapping Genres.

Querying a GraphQL field marked with a `@cypher` directive executes that query as a subquery:

*GraphQL:*
~~~graphql
{
  Movie(title: "River Runs Through It, A") {
    title
    year
    imdbRating
    actors {
      name
    }
    similar(first: 3) {
      title
    }
  }
}
~~~

*Cypher:*
~~~cypher
MATCH (movie:Movie {title: "River Runs Through It, A"})
RETURN movie { .title , .year , .imdbRating,
  actors: [(movie)<-[:ACTED_IN]-(movie_actors:Actor) | movie_actors { .name }],
  similar: [ x IN apoc.cypher.runFirstColumn("
        WITH {this} AS this
        MATCH (this)-[:IN_GENRE]->(:Genre)<-[:IN_GENRE]-(o:Movie)
        RETURN o",
        {this: movie}, true) | x { .title }][..3]
} AS movie
SKIP 0
~~~


### Query Neo4j

Inject a Neo4j driver instance in the context of each GraphQL request and `neo4j-graphql-py` will query the Neo4j database and return the results to resolve the GraphQL query.

~~~python
from neo4j_graphql_py import make_executable_schema
schema = make_executable_schema(type_defs, resolvers)
~~~

~~~python
import neo4j
def context(request):
    global driver
    if driver is None:
        driver = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

    return {'driver': driver, 'request': request}
~~~

~~~python
from ariadne.asgi import GraphQL
import uvicorn
rootValue = {}
app = GraphQL(schema=schema, root_value=rootValue, context_value=context, debug=True)
uvicorn.run(app)
~~~

See [/examples](https://github.com/Usama0121/neo4j-graphql-py/tree/master/examples/ariadne_uvicorn) for complete examples using different GraphQL server libraries.


## Benefits

* Send a single query to the database
* No need to write queries for each resolver
* Exposes the power of the Cypher query language through GraphQL

## Examples

See [/examples](https://github.com/Usama0121/neo4j-graphql-py/tree/master/examples) for complete examples using different GraphQL server libraries.