const REGEX_MAIUSCULA = /[A-Z]/;
const REGEX_MINUSCULA = /[a-z]/;
const REGEX_DIGITO = /\d/;
const REGEX_ESPECIAL = /[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]/;

export function hasSpecialChar(senha: string): boolean {
  return REGEX_ESPECIAL.test(senha);
}

export function validarSenha(senha: string): { valida: boolean; erros: string[] } {
  const erros: string[] = [];

  if (senha.length < 12) {
    erros.push("Senha deve ter no minimo 12 caracteres");
  }
  if (senha.length > 64) {
    erros.push("Senha deve ter no maximo 64 caracteres");
  }
  if (!REGEX_MAIUSCULA.test(senha)) {
    erros.push("Senha deve ter pelo menos uma letra maiuscula");
  }
  if (!REGEX_MINUSCULA.test(senha)) {
    erros.push("Senha deve ter pelo menos uma letra minuscula");
  }
  if (!REGEX_DIGITO.test(senha)) {
    erros.push("Senha deve ter pelo menos um numero");
  }
  if (!REGEX_ESPECIAL.test(senha)) {
    erros.push("Senha deve ter pelo menos um caractere especial");
  }

  return { valida: erros.length === 0, erros };
}
