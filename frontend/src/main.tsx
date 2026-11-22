import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Open-licence fonts bundled locally (no CDN): Barlow for the VALORANT-like UI, Saira Semi Condensed for CS2.
import "@fontsource/barlow/400.css";
import "@fontsource/barlow/500.css";
import "@fontsource/barlow/600.css";
import "@fontsource/barlow-semi-condensed/500.css";
import "@fontsource/barlow-semi-condensed/600.css";
import "@fontsource/barlow-semi-condensed/700.css";
import "@fontsource/saira-semi-condensed/500.css";
import "@fontsource/saira-semi-condensed/600.css";
import "@fontsource/saira-semi-condensed/700.css";
import "./styles/base.css";
import "./styles/valorant.css";
import "./styles/cs2.css";
import "./styles/adaptive.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
