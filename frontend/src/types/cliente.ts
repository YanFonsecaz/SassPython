export interface PersonaGlobal {
  tom_voz: string;
  nivel_tecnico: string;
  estilo_escrita: string;
  instrucoes_gerais: string;
  exemplos_textos: string[];
}

export interface Persona {
  nome: string;
  tom_voz: string;
  nivel_tecnico: string;
  estilo_escrita: string;
  objetivo: string;
  palavras_proibidas: string[];
  palavras_recomendadas: string[];
  instrucoes_gerais: string;
}

export interface ConfigJson {
  persona_global: PersonaGlobal;
  personas: Persona[];
}

export interface Cliente {
  id: string;
  nome: string;
  site_url: string | null;
  config_json: ConfigJson;
  ativo: boolean;
  criado_em: string;
  atualizado_em: string;
}

export interface ClienteCreate {
  nome: string;
  site_url?: string | null;
  config_json?: ConfigJson;
}

export interface ClienteUpdate {
  nome?: string;
  site_url?: string | null;
  config_json?: ConfigJson;
}
