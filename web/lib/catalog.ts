import { Pool } from "pg";
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
export async function patients() {
  const { rows } = await pool.query(
    "SELECT patient_id AS id, label, fixture FROM patient_catalog ORDER BY patient_id",
  );
  return rows;
}

export async function modelMetadata() {
  const { rows } = await pool.query("SELECT metadata FROM model_metadata WHERE singleton");
  const metadata = rows[0]?.metadata;
  if (!metadata) return null;
  const table = await pool.query("SELECT to_regclass('model_evaluation') AS name");
  if (table.rows[0]?.name) {
    const result = await pool.query("SELECT evaluation FROM model_evaluation WHERE model_version=$1", [metadata.model_version]);
    if (result.rows[0]) metadata.evaluation = result.rows[0].evaluation;
  }
  return metadata;
}
