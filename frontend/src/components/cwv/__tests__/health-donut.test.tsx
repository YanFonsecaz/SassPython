import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

import { HealthDonut } from "@/components/cwv/auditoria/health-donut";

describe("HealthDonut", () => {
  it("mostra % central e contadores", () => {
    render(<HealthDonut pass={85} fail={91} label="Before" />);
    expect(screen.getByText("48%")).toBeInTheDocument();
    expect(screen.getByText(/85/)).toBeInTheDocument();
    expect(screen.getByText(/91/)).toBeInTheDocument();
    expect(screen.getByText("Before")).toBeInTheDocument();
  });

  it("estado vazio com hint", () => {
    render(<HealthDonut pass={null} fail={null} label="After" hint="aguardando re-auditoria" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("aguardando re-auditoria")).toBeInTheDocument();
  });
});
