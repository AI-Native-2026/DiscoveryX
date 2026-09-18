import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import App from "./App";
import { I18nProvider } from "./i18n";
import "./console.css";
import "./styles.css";

document.documentElement.setAttribute("data-theme", "dark");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <HashRouter>
        <App />
      </HashRouter>
    </I18nProvider>
  </React.StrictMode>,
);
