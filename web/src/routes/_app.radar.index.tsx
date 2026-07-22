import { createFileRoute } from "@tanstack/react-router";
import { RadarPage } from "./_app.radar";

export const Route = createFileRoute("/_app/radar/")({
  component: RadarPage,
});
