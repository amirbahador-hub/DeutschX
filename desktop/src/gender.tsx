// Gender colour-coding for German nouns — a classic memory aid.
// Convention: der = blue, die = rose, das = green (see .g-der/.g-die/.g-das in App.css).

// Strip stray markdown/whitespace some older cards carry (e.g. "**der Mann **").
export function cleanTerm(s: string): string {
  return s.replace(/[*_`]/g, " ").replace(/\s+/g, " ").trim();
}

export function genderOf(term: string): "der" | "die" | "das" | null {
  const m = cleanTerm(term).match(/^(der|die|das)\b/i);
  return m ? (m[1].toLowerCase() as "der" | "die" | "das") : null;
}

// Render a German term with its leading article tinted by gender.
// `tintWhole` colours the whole noun (nice for big headwords), not just the article.
export function GermanTerm({
  text,
  className,
  tintWhole = false,
}: {
  text: string;
  className?: string;
  tintWhole?: boolean;
}) {
  const clean = cleanTerm(text);
  const m = clean.match(/^(der|die|das)\s+(.*)$/i);
  if (!m) return <span className={className}>{clean}</span>;
  const g = m[1].toLowerCase();
  return (
    <span className={(className ?? "") + (tintWhole ? ` g-${g}` : "")}>
      <span className={`g-${g}`}>{m[1]}</span> {m[2]}
    </span>
  );
}

// A small "der die das" key so the colours are self-explanatory.
export function GenderLegend() {
  return (
    <span className="gender-legend" title="Noun gender colours">
      <span className="g-der">der</span>
      <span className="g-die">die</span>
      <span className="g-das">das</span>
    </span>
  );
}
