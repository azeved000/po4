"""RubberTech — programação da produção de correias transportadoras por PLI.

Problema ``R_m | s_ij, M_i | Σ w_i T_i``: máquinas paralelas não relacionadas,
setup dependente da sequência (assimétrico), elegibilidade restrita de máquinas
e minimização do atraso total ponderado.

**Restrição metodológica do trabalho:** a solução entregue é obtida por
Programação Linear Inteira Mista. As regras de despacho em :mod:`baselines`
existem apenas como referência de comparação para o relatório.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
