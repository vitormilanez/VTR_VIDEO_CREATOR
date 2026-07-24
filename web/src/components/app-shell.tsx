import type { ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Radar,
  Lightbulb,
  FileText,
  Film,
  CalendarDays,
  Clock3,
  BarChart3,
  Settings,
  PanelsTopLeft,
  ScanFace,
  Scissors,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  SidebarHeader,
} from "@/components/ui/sidebar";
import { ComplianceBanner } from "./compliance";
import { useStore } from "@/lib/store";

interface NavItem {
  title: string;
  url: string;
  icon: typeof LayoutDashboard;
  exact?: boolean;
}

// Sidebar agrupada por etapa do funil: criar -> produzir -> distribuir.
const navGroups: Array<{ label: string | null; items: NavItem[] }> = [
  {
    label: null,
    items: [{ title: "Dashboard", url: "/", icon: LayoutDashboard, exact: true }],
  },
  {
    label: "Criacao",
    items: [
      { title: "Radar de tendencias", url: "/radar", icon: Radar },
      { title: "Ideias", url: "/ideias", icon: Lightbulb },
      { title: "Roteiros", url: "/roteiros", icon: FileText },
    ],
  },
  {
    label: "Producao",
    items: [
      { title: "Producao de videos", url: "/producao", icon: Film },
      { title: "Cortes", url: "/cortes", icon: Scissors },
      { title: "Avatares", url: "/avatares", icon: ScanFace },
      { title: "Pack de conteudo", url: "/packs", icon: PanelsTopLeft },
    ],
  },
  {
    label: "Distribuicao",
    items: [
      { title: "Calendario", url: "/calendario", icon: CalendarDays },
      { title: "Performance", url: "/performance", icon: BarChart3 },
    ],
  },
  {
    label: "Sistema",
    items: [{ title: "Configuracoes", url: "/configuracoes", icon: Settings }],
  },
];

function AppSidebar() {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  const isActive = (url: string, exact?: boolean) =>
    exact ? pathname === url : pathname === url || pathname.startsWith(url + "/");

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="border-b border-sidebar-border px-3 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-linear-to-br from-sidebar-primary to-status-success text-primary font-display text-sm font-bold shadow-sm">
            AV
          </div>
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <div className="truncate font-display text-sm font-semibold leading-tight text-sidebar-foreground">
              AI Video Creator
            </div>
            <div className="truncate text-[11px] text-sidebar-foreground/60">VTR</div>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        {navGroups.map((group) => (
          <SidebarGroup key={group.label ?? "root"} className={group.label ? "" : "pb-0"}>
            {group.label ? (
              <SidebarGroupLabel className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/50">
                {group.label}
              </SidebarGroupLabel>
            ) : null}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.url}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(item.url, item.exact)}
                      tooltip={item.title}
                      className="data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-primary data-[active=true]:font-semibold"
                    >
                      <Link to={item.url}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
    </Sidebar>
  );
}

export function AppShell({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const syncedAt = useStore((state) => state.syncedAt);

  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full bg-background">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <ComplianceBanner />
          <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b bg-card/80 px-4 backdrop-blur-md">
            <SidebarTrigger />
            <div className="h-4 w-px bg-border" />
            <h1 className="truncate font-display text-base font-semibold tracking-tight">
              {title}
            </h1>
            <div className="ml-auto flex items-center gap-2">
              <SyncStatus syncedAt={syncedAt} />
              {actions}
            </div>
          </header>
          <main className="flex-1 overflow-x-hidden p-4 md:p-6">{children}</main>
        </div>
      </div>
    </SidebarProvider>
  );
}

function SyncStatus({ syncedAt }: { syncedAt: string | null }) {
  if (!syncedAt) {
    return (
      <span className="hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] text-muted-foreground md:inline-flex">
        <Clock3 className="h-3.5 w-3.5" />
        Aguardando Sheets
      </span>
    );
  }
  return (
    <span className="hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] text-muted-foreground md:inline-flex">
      <Clock3 className="h-3.5 w-3.5" />
      Sheets {formatSyncTime(syncedAt)}
    </span>
  );
}

function formatSyncTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "sincronizado";
  const diffMs = Date.now() - date.getTime();
  const absMinutes = Math.max(0, Math.floor(diffMs / 60000));
  if (absMinutes < 1) return "agora";
  if (absMinutes < 60) return `ha ${absMinutes} min`;
  const absHours = Math.floor(absMinutes / 60);
  if (absHours < 24) return `ha ${absHours} h`;
  return date.toLocaleDateString("pt-BR");
}
