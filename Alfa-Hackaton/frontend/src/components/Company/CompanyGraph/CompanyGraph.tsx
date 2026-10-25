import type { Client } from "@/src/types";

interface GraphNode {
  label: string;
  subtitle: string;
  amount?: string;
  payer?: boolean;
  group?: boolean;
}

const CompanyGraph = ({ client }: { client: Client }) => {
  const nodes: GraphNode[] = [
    ...client.counter.map(([label, subtitle, amount, role]) => ({
      label,
      subtitle,
      amount,
      payer: role === "Плательщик",
    })),
    ...Array.from(
      { length: Math.min(client.groupSize - 1, 3) },
      (_, index) => ({
        label: `${client.group}-${index + 2}`,
        subtitle: "Компания группы",
        group: true,
      }),
    ),
  ];

  return (
    <svg
      viewBox="0 0 800 300"
      width="100%"
      role="img"
      aria-label={`Граф связей компании ${client.name}`}
    >
      {nodes.map((node, index) => {
        const angle = -Math.PI / 2 + (index * 2 * Math.PI) / nodes.length;
        const x = 400 + Math.cos(angle) * 290;
        const y = 150 + Math.sin(angle) * 115;
        const color = node.group
          ? "var(--ink-3)"
          : node.payer
            ? "var(--green)"
            : "var(--red)";
        return (
          <g key={node.label}>
            <line
              x1={400}
              y1={150}
              x2={x}
              y2={y}
              stroke={color}
              strokeWidth={node.group ? 1 : 2}
              strokeDasharray={node.group ? "4 4" : undefined}
            />
            <rect
              x={x - 80}
              y={y - 20}
              width={160}
              height={40}
              rx={10}
              fill="#fff"
              stroke={color}
            />
            <text x={x} y={y - 3} textAnchor="middle" fontWeight={600}>
              {node.label}
              {node.amount ? ` · ${node.amount}` : ""}
            </text>
            <text x={x} y={y + 12} textAnchor="middle" fill="var(--ink-3)">
              {node.subtitle}
            </text>
          </g>
        );
      })}
      <rect x={305} y={128} width={190} height={44} rx={12} fill="var(--ink)" />
      <text x={400} y={155} textAnchor="middle" fill="#fff" fontWeight={700}>
        {client.name.replace(/^(ООО|АО) /, "").slice(0, 26)}
      </text>
    </svg>
  );
};

export default CompanyGraph;
