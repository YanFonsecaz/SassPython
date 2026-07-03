"""Constantes compartilhadas entre os workflows de inlinks (Receber e Distribuir).

Centralizar os pisos decisórios evita a assimetria histórica em que cada pipeline
irmão mantinha o próprio corte de cosine — fonte de bugs sutis quando um muda e o
outro não (ver SPEC_Distribuir_Viabilidade_Pelo_Juiz).
"""

# Piso de RUÍDO: corta apenas domínio claramente alheio. A decisão de qualidade
# é do LLM juiz (julgamento único) — o cosine não decide mais.
# Caso real que motivou o valor: sinônimo legítimo "dropshipping" x "loja virtual"
# media cosine 0.26 e era morto pelo piso anterior de 0.40.
PISO_RUIDO_SEMANTICO = 0.25

# Teto de páginas indexadas por cliente na descoberta automática (SPEC de Descoberta).
MAX_PAGINAS_SITE = 500
