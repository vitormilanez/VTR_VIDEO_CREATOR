import { createFileRoute } from "@tanstack/react-router";
import { IdeiasPage } from "./_app.ideias";

export const Route = createFileRoute("/_app/ideias/")({
  component: IdeiasPage,
});
