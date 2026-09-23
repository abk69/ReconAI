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
      { label: "Documents", href: "/documents", available: false },
      { label: "Purchase Orders", href: "/purchase-orders", available: false },
      { label: "Goods Receipts", href: "/goods-receipts", available: false },
      { label: "Invoices", href: "/invoices", available: false },
      { label: "Reconciliation", href: "/reconciliation", available: false },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { label: "Exceptions", href: "/exceptions", available: false },
      { label: "Risk & Anomalies", href: "/risk", available: false },
      { label: "Policy Intelligence", href: "/policies", available: false },
    ],
  },
  {
    id: "workflow",
    label: "Workflow",
    items: [
      { label: "Review Center", href: "/review", available: false },
      { label: "Resolution", href: "/resolution", available: false },
    ],
  },
];

export function findNavItem(pathname: string): NavItem | undefined {
  return navigation.flatMap((section) => section.items).find((item) => item.href === pathname);
}
