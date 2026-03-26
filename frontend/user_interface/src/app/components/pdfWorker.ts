import { pdfjs } from "react-pdf";

const baseUrl = String(import.meta.env.BASE_URL || "/");
const normalizedBaseUrl = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
const pdfWorkerUrl = `${normalizedBaseUrl}pdf.worker.min.mjs`;

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export { pdfWorkerUrl };
