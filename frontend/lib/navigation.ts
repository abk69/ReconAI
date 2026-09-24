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
    ],
  },
  {
    id: "reconciliation",
    label: "Reconciliation",
    items: [
      { label: "Reconciliation", href: "/reconciliation", available: true },
      { label: "Exceptions", href: "/exceptions", available: true },
      { label: "Review", href: "/review", available: true },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { label: "Risk", href: "/risk", available: true },
      { label: "Policies", href: "/policies", available: true },
      { label: "Resolution", href: "/resolution", available: true },
    ],
  },
];

export function findNavItem(pathname: string): { section: NavSection; item: NavItem } | undefined {
  const matches = navigation.flatMap((section) =>
    section.items
      .filter((item) => pathname === item.href || pathname.startsWith(`${item.href}/`))
      .map((item) => ({ section, item })),
  );
  return matches.sort((left, right) => right.item.href.length - left.item.href.length)[0];
}
