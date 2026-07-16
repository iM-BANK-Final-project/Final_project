import { useState } from "react";

export default function ExpandableText({
  text,
  label,
  className = "",
  lines = 1,
  collapsedLength = 8,
  as: Element = "span"
}) {
  const [expanded, setExpanded] = useState(false);
  const value = text == null || text === "" ? "-" : String(text);
  const visibleValue = expanded ? value : value.slice(0, collapsedLength);
  const classes = [
    "expandable-text",
    expanded ? "is-expanded" : "",
    className
  ].filter(Boolean).join(" ");

  return (
    <Element
      className={classes}
      style={{ "--collapsed-lines": lines }}
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      aria-label={`${label} ${expanded ? "접기" : "전체 보기"}: ${value}`}
      title={value}
      onClick={() => setExpanded((current) => !current)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          setExpanded((current) => !current);
        }
      }}
    >
      {visibleValue}
    </Element>
  );
}
