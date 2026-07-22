import { useEffect } from "react";
import { Outlet, createFileRoute } from "@tanstack/react-router";
import { useStore } from "@/lib/store";
import { fetchState } from "@/lib/api/local";

function AppData() {
  const hydrate = useStore((s) => s.hydrate);

  useEffect(() => {
    let cancelled = false;
    fetchState()
      .then((data) => {
        if (!cancelled) hydrate(data);
      })
      .catch((err) => {
        // API offline: mantem os seeds locais e apenas registra o aviso.
        console.warn("[AI Video Creator] API local indisponivel, usando seeds:", err);
      });
    return () => {
      cancelled = true;
    };
  }, [hydrate]);

  return <Outlet />;
}

export const Route = createFileRoute("/_app")({
  component: AppData,
});
