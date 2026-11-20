import Workspace from "./Workspace";
import { curatedExamples } from "../../lib/examples";

export default async function WorkspacePage({
  searchParams,
}: {
  searchParams: Promise<{ example?: string | string[] }>;
}) {
  const { example } = await searchParams;
  return <Workspace showCompletedExample={example === "completed"} examples={curatedExamples} />;
}
