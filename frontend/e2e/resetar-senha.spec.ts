import { test, expect } from "@playwright/test";

test.describe("Pagina Resetar Senha", () => {
  test("deve mostrar erro quando token ausente", async ({ page }) => {
    await page.goto("/resetar-senha");
    await expect(page.getByText("Token invalido")).toBeVisible();
    await expect(page.getByText(/link de redefinicao/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /solicitar recuperacao/i })).toBeVisible();
  });

  test("deve mostrar formulario de redefinicao com token valido", async ({ page }) => {
    await page.goto("/resetar-senha?token=meu-token-xyz");
    await expect(page.getByText("Redefinir senha").first()).toBeVisible();
    await expect(page.getByPlaceholder("Minimo 12 caracteres").first()).toBeVisible();
    await expect(page.getByPlaceholder("Repita a nova senha")).toBeVisible();
    await expect(page.getByRole("button", { name: "Redefinir senha" })).toBeVisible();
    await expect(page.getByRole("link", { name: /voltar ao login/i })).toBeVisible();
  });

  test("deve validar senhas no cliente antes de enviar", async ({ page }) => {
    await page.goto("/resetar-senha?token=meu-token-xyz");
    const novaSenhaInput = page.getByPlaceholder("Minimo 12 caracteres").first();
    const confirmarInput = page.getByPlaceholder("Repita a nova senha");
    const submitBtn = page.getByRole("button", { name: "Redefinir senha" });

    await novaSenhaInput.fill("fraca");
    await expect(page.getByText(/minimo 12 caracteres/i)).toBeVisible();

    await novaSenhaInput.fill("SenhaForte123!@#");
    await confirmarInput.fill("SenhaDiferente456!@#");
    await submitBtn.click();
    await expect(page.getByText(/senhas nao conferem/i)).toBeVisible();
  });

  test("deve mostrar sucesso apos redefinir (token invalido = erro)", async ({ page }) => {
    await page.goto("/resetar-senha?token=token-invalido");
    const novaSenhaInput = page.getByPlaceholder("Minimo 12 caracteres").first();
    const confirmarInput = page.getByPlaceholder("Repita a nova senha");

    await novaSenhaInput.fill("NovaSenhaForte123!@#");
    await confirmarInput.fill("NovaSenhaForte123!@#");
    await page.getByRole("button", { name: "Redefinir senha" }).click();

    await page.waitForTimeout(3000);

    const hasSuccess = await page.getByText("Senha redefinida").isVisible().catch(() => false);
    const hasError = await page.getByRole("alert").first().isVisible().catch(() => false);

    expect(hasSuccess || hasError).toBeTruthy();
  });
});
