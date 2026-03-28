type Span = {
  setAttributes: (_attributes: Record<string, unknown>) => void;
  end: () => void;
};

type Tracer = {
  startSpan: (_name: string, _options?: Record<string, unknown>) => Span;
};

const noopSpan: Span = {
  setAttributes: () => {},
  end: () => {},
};

const noopTracer: Tracer = {
  startSpan: () => noopSpan,
};

export const trace = {
  getTracer: (_serviceName?: string): Tracer => noopTracer,
};

export default { trace };
