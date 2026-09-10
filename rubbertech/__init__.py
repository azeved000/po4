"""RubberTech — programação da produção de correias transportadoras por PLI.

Problema ``R_m | s_ij, M_i | Σ w_i T_i``: máquinas paralelas não relacionadas,
setup dependente da sequência (assimétrico), elegibilidade restrita de máquinas
e minimização do atraso total ponderado.

**Restrição metodológica do trabalho:** a solução entregue é obtida por
Programação Linear Inteira Mista. A regra EDD em :mod:`conferencia` existe
apenas como referência de comparação para o relatório.

Regra de dependência entre os módulos (o que mantém a verificação honesta)::

    dados        -> (nada)
    modelo       -> dados            [+ PuLP]
    conferencia  -> dados            [sem PuLP, sem modelo]
    relatorio    -> dados            [+ matplotlib]
    main         -> todos

``conferencia`` não pode importar ``modelo`` nem PuLP: é isso que faz do
avaliador e da força bruta uma segunda opinião de verdade, e não um eco do
solver.
"""

from __future__ import annotations

__version__ = "2.0.0"

__all__ = ["__version__"]
