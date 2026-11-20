import type { ReactNode } from "react";

export default function BetaModelResults({ children }: { children: ReactNode }) {
  return (
    <details className="prototype-results" id="prototype-model">
      <summary><h2>Survival model <span className="model-beta">Beta</span></h2></summary>
      <p>The scoring and evaluation pipeline is in place. The survival model is still being tuned, and its risk rankings may be inaccurate. These results are for research demonstration only.</p>
      {children}
    </details>
  );
}
