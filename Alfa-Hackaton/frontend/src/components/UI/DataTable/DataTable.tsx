import type { ReactNode } from "react";
import styles from "./DataTable.module.css";

interface DataTableProps {
  headers: ReactNode[];
  rows: ReactNode[][];
  caption?: string;
}

const DataTable = ({ headers, rows, caption }: DataTableProps) => (
  <div className={styles.scroll} tabIndex={0}>
    <table>
      {caption && <caption className={styles.caption}>{caption}</caption>}
      <thead>
        <tr>
          {headers.map((header, index) => (
            <th key={index} scope="col">
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {row.map((cell, cellIndex) => (
              <td key={cellIndex}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default DataTable;
