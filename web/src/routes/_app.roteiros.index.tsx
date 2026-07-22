import { createFileRoute } from "@tanstack/react-router";
import { RoteirosPage } from "./_app.roteiros";

export const Route = createFileRoute("/_app/roteiros/")({
  component: RoteirosPage,
});
