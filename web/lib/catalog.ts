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
  return rows[0]?.metadata ?? null;
}
