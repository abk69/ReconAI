export type NavItem = {
  label: string;
  href: string;
  available: boolean;
};

export type NavSection = {
  id: string;
  label: string;
  items: NavItem[];
};

export const navigation: NavSection[] = [
  {
    id: "overview",
    label: "Overview",
    items: [{ label: "Dashboard", href: "/dashboard", available: true }],
  },
  {
    id: "procurement",
    label: "Procurement",
    items: [
      { label: "Documents", href: "/documents", available: true },
      { label: "Purchase Orders", href: "/purchase-orders", available: true },
      { label: "Goods Receipts", href: "/goods-receipts", available: true },
      { label: "Invoices", href: "/invoices", available: true },
      { label: "Reconciliation", href: "/reconciliation", available: true },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { label: "Exceptions", href: "/exceptions", available: true },
      { label: "Risk & Anomalies", href: "/risk", available: true },
      { label: "Policy Intelligence", href: "/policies", available: false },
    ],
  },
  {
    id: "workflow",
    label: "Workflow",
    items: [
      { label: "Review Center", href: "/review", available: true },
      { label: "Resolution", href: "/resolution", available: true },
    ],
  },
];

export function findNavItem(pathname: string): NavItem | undefined {
  return navigation.flatMap((section) => section.items).find((item) => item.href === pathname);
}
