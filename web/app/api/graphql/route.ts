import { ApolloServer } from "@apollo/server";
import { HeaderMap } from "@apollo/server";
import { patients, modelMetadata } from "../../../lib/catalog";
const server = new ApolloServer({
  typeDefs: `
    type Patient { id: ID!, label: String!, fixture: Boolean! }
    type ModelMetadata {
      model_version: String!, feature_version: String!, feature_schema: [String!]!,
      development_count: Int!, held_out_count: Int!, partition_sha256: String!,
      reference_count: Int!, reference_median: Float!, score_definition: String!, evaluation: Evaluation, percentile_rule: String, reference_cohort: String
    }
    type Exclusion { patient_id: ID!, code: String!, message: String! }
    type Point { time: Float!, survival: Float! }
    type Curve { group: String!, count: Int!, events: Int!, points: [Point!]! }
    type Uncertainty { context: String!, method: String, interval: [Float!], estimable_samples: Int, unestimable_samples: Int, requested_samples: Int }
    type Evaluation { evaluation_version: String, model_version: String, scope: String, c_index: Float, evaluated_count: Int, selected_count: Int, held_out_count: Int, event_count: Int, censored_count: Int, unavailable_reason: String, method: String, time_unit: String, curves: [Curve!], curve_context: String, exclusions: [Exclusion!], uncertainty: Uncertainty }
    type RiskScore { patient_id: ID!, risk_score: Float!, model_version: String!, feature_version: String!, score_definition: String!, risk_percentile: Float, risk_group: String }
    type RunResults { id: ID!, status: String!, patient_ids: [ID!]!, model_version: String, scores: [RiskScore!]!, evaluation: Evaluation }
    type Query { patients: [Patient!]!, modelMetadata: ModelMetadata, runResults(id: ID!): RunResults! }
  `,
  resolvers: { Query: { patients, modelMetadata,
    runResults: async (_: unknown, { id }: { id: string }, context: { authorization: string }) => {
      if (!process.env.RUNNER_URL) throw Error("Runner service is not configured");
      const response = await fetch(`${process.env.RUNNER_URL.replace(/\/$/, "")}/runs/${encodeURIComponent(id)}/results`, {
        headers: { Authorization: context.authorization }, cache: "no-store",
      });
      if (!response.ok) throw Error(response.status === 403 ? "Run access denied" : "Temporary run results unavailable");
      return response.json();
    },
  } },
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
    context: async () => ({ authorization: request.headers.get("Authorization") || "" }),
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
