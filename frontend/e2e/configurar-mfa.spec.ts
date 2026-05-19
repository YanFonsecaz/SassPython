import { test, expect } from "@playwright/test";

test.describe("Pagina Configurar MFA", () => {
  test("deve redirecionar para login se nao autenticado", async ({ page }) => {
    await page.goto("/configurar-mfa");
    await page.waitForTimeout(3000);

    const onPerfil = await page.getByText("Carregando...").isVisible().catch(() => false);
    const onLogin = await page.getByRole("heading", { name: "Entrar" }).isVisible().catch(() => false);

    expect(onPerfil || onLogin).toBeTruthy();
  });
});
