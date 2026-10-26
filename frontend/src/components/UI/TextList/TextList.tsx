const TextList = ({
  items,
  ordered = false,
}: {
  items: string[];
  ordered?: boolean;
}) => {
  if (!items.length) return <p style={{ color: "var(--ink-3)" }}>—</p>;
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag style={{ margin: "6px 0", paddingLeft: 18 }}>
      {items.map((item) => (
        <li key={item} style={{ margin: "4px 0" }}>
          {item}
        </li>
      ))}
    </Tag>
  );
};

export default TextList;
