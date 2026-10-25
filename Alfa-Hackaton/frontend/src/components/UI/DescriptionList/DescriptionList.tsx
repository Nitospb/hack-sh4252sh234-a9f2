const DescriptionList = ({ items }: { items: [string, string][] }) => (
  <ul style={{ margin: 0, paddingLeft: 18, color: "var(--ink-2)" }}>
    {items.map(([label, text]) => (
      <li key={label} style={{ margin: "6px 0" }}>
        <b>{label}:</b> {text}
      </li>
    ))}
  </ul>
);

export default DescriptionList;
