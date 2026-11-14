type PlaceholderPanelProps = {
  title: string;
  milestone: string;
  description: string;
};

export function PlaceholderPanel({
  title,
  milestone,
  description,
}: PlaceholderPanelProps) {
  return (
    <section className="animate-rise border-t border-line/70 pt-5">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-xl text-ink">{title}</h2>
        <span className="text-xs uppercase tracking-[0.16em] text-muted">
          {milestone}
        </span>
      </div>
      <p className="max-w-prose text-sm leading-6 text-ink-soft">{description}</p>
    </section>
  );
}
