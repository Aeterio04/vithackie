import React from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "./Skeleton";

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render?: (row: T) => React.ReactNode;
  className?: string;
  headerClassName?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  isLoading?: boolean;
  emptyState?: React.ReactNode;
  onRowClick?: (row: T) => void;
  className?: string;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  isLoading = false,
  emptyState,
  onRowClick,
  className,
}: DataTableProps<T>) {
  return (
    <div
      className={cn(
        "w-full overflow-x-auto rounded-[16px] border border-[#E3DACC] bg-white shadow-xs",
        className
      )}
    >
      <table className="w-full text-left text-sm border-collapse">
        <thead>
          <tr className="border-b border-[#E3DACC] bg-[#FAF9F5] text-xs font-medium text-[#6B6A64]">
            {columns.map((col) => (
              <th
                key={col.key}
                className={cn("px-4 py-3 font-semibold", col.headerClassName)}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>

        <tbody className="divide-y divide-[#E3DACC]/60">
          {isLoading ? (
            Array.from({ length: 4 }).map((_, rIdx) => (
              <tr key={rIdx}>
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3.5">
                    <Skeleton className="h-4 w-3/4" />
                  </td>
                ))}
              </tr>
            ))
          ) : data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center">
                {emptyState || (
                  <span className="text-xs text-[#8A887F]">No data found</span>
                )}
              </td>
            </tr>
          ) : (
            data.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                onClick={() => onRowClick?.(row)}
                className={cn(
                  "hover:bg-[#FAF9F5]/70 transition-colors",
                  onRowClick && "cursor-pointer"
                )}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      "px-4 py-3.5 text-xs text-[#141413] align-middle",
                      col.className
                    )}
                  >
                    {col.render
                      ? col.render(row)
                      : (row[col.key] as React.ReactNode) ?? "-"}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
