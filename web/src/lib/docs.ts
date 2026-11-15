// Developer docs (docs/*.md in the repo), exported by scripts/export_site_data.py.
import index from "../generated/docs.json";

export interface DocPage {
  slug: string;
  title: string;
  description: string;
}

export const docs: DocPage[] = index;

const raw = import.meta.glob<string>("../generated/docs/*.md", { query: "?raw", import: "default", eager: true });

/** A doc's Markdown source, as served at /docs/<slug>.md. */
export const docMarkdown = (slug: string): string => raw[`../generated/docs/${slug}.md`] ?? "";
