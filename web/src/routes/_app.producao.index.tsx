import { createFileRoute } from "@tanstack/react-router";
import { ProducaoPage } from "./_app.producao";

export const Route = createFileRoute("/_app/producao/")({
  component: ProducaoPage,
});
