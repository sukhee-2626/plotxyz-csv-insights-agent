export type FieldType = "text" | "textarea" | "number" | "checkbox";

export interface AgentField {
  name: string;
  label: string;
  type: FieldType;
  rows?: number;
  placeholder?: string;
}

export interface AgentConfig {
  slug: string;
  title: string;
  tagline: string;
  purpose: string;
  accent: string;
  features: string[];
  limitations: string[];
  fields: AgentField[];
  sample: Record<string, string | number | boolean>;
  repo: string;
}

export const agent: AgentConfig = {
  "slug": "plotxyz-csv-insights-agent",
  "title": "CSV Insights",
  "tagline": "A profile of your data in one pass.",
  "purpose": "Computes column statistics, numeric correlations, categorical leaders, and a histogram for the first numeric column.",
  "accent": "#34d399",
  "features": [
    "Numeric and categorical profiling",
    "Correlation table",
    "Histogram chart data"
  ],
  "limitations": [
    "Statistics describe the supplied sample only.",
    "Correlation is not causation; non-linear relationships may be missed."
  ],
  "fields": [
    {
      "name": "csv",
      "label": "CSV data",
      "type": "textarea",
      "rows": 10,
      "placeholder": ""
    }
  ],
  "sample": {
    "csv": "month,revenue,orders,channel\nJan,1200,30,web\nFeb,1500,36,web\nMar,900,22,partner\nApr,1800,44,web"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-csv-insights-agent"
};
