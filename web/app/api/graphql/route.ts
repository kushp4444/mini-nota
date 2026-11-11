import { ApolloServer } from "@apollo/server";
import { HeaderMap } from "@apollo/server";
import { patients } from "../../../lib/catalog";
const server = new ApolloServer({
  typeDefs: `type Patient { id: ID!, label: String!, fixture: Boolean! } type Query { patients: [Patient!]! }`,
  resolvers: { Query: { patients } },
});
const started = server.start();
export async function POST(request: Request) {
  await started;
  const headers = new HeaderMap();
  request.headers.forEach((v, k) => headers.set(k, v));
  const result = await server.executeHTTPGraphQLRequest({
    httpGraphQLRequest: {
      method: "POST",
      headers,
      search: "",
      body: await request.json(),
    },
    context: async () => ({}),
  });
  if (result.body.kind !== "complete")
    return new Response("Unsupported response", { status: 500 });
  return new Response(result.body.string, {
    status: result.status || 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}
