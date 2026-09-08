"""
Projeto 1 - RubberTech / EP58D - Programacao de Operacoes
Modelo de Programacao Linear Inteira Mista (PLI)

    R_m | s_ij, M_i | sum(w_i * T_i)

Maquinas paralelas nao relacionadas, elegibilidade restrita,
setup dependente da sequencia, atraso total ponderado.

Formulacao alinhada a Arenales et al. (2015, cap. 3):
variavel de sucessor imediato + no ficticio 0 + restricoes
disjuntivas com big-M + eliminacao de subciclos (MTZ).
"""

from dataclasses import dataclass, field
import pulp


# ----------------------------------------------------------------------
# 1. ESTRUTURA DE DADOS DA INSTANCIA
# ----------------------------------------------------------------------

@dataclass
class Instancia:
    """Dados de entrada do problema."""
    n: int                      # numero de itens
    m: int                      # numero de linhas
    p: dict                     # p[(i,k)] tempo de processamento do item i na linha k
    s: dict                     # s[(i,j)] setup do item j apos o item i (i=0 -> setup inicial)
    d: dict                     # d[i] data de entrega
    w: dict                     # w[i] peso (multa + criticidade do cliente)
    E: dict                     # E[i] conjunto de linhas elegiveis para o item i
    nomes: dict = field(default_factory=dict)

    @property
    def J(self):
        """Itens."""
        return list(range(1, self.n + 1))

    @property
    def J0(self):
        """Itens + no ficticio 0 (inicio da linha)."""
        return [0] + self.J

    @property
    def M(self):
        """Linhas de producao."""
        return list(range(1, self.m + 1))

    def big_M(self):
        """
        Cota superior valida para o horizonte: soma do maior tempo de
        processamento com o maior setup de cada item. Big-M justo evita
        relaxacao linear fraca.
        """
        total = 0
        for i in self.J:
            total += max(self.p[(i, k)] for k in self.E[i])
            total += max(self.s[(a, i)] for a in self.J0 if a != i)
        return total + max(self.d.values())


# ----------------------------------------------------------------------
# 2. CONSTRUCAO DO MODELO
# ----------------------------------------------------------------------

def construir_modelo(inst: Instancia, mtz: bool = True,
                     penalidade_antecipacao: dict | None = None):
    """
    Monta o modelo PLI.

    mtz: se True, inclui as restricoes de Miller-Tucker-Zemlin (1960).
         As restricoes de tempo (4) ja impedem subciclos, mas o MTZ
         fortalece a relaxacao linear.
    penalidade_antecipacao: dict alpha[i]. Se fornecido, acrescenta
         sum(alpha_i * E_i) ao objetivo, tratando a area de estocagem
         limitada por meio de um criterio just-in-time (secao 5.6).
    """
    J, J0, M = inst.J, inst.J0, inst.M
    V = inst.big_M()

    mod = pulp.LpProblem("RubberTech", pulp.LpMinimize)

    # ---- Variaveis de decisao ----------------------------------------
    # x[i,k] = 1 se o item i e produzido na linha k  (so existe se k elegivel)
    x = {(i, k): pulp.LpVariable(f"x_{i}_{k}", cat="Binary")
         for i in J for k in inst.E[i]}

    # y[i,j,k] = 1 se j e produzido imediatamente apos i na linha k
    y = {(i, j, k): pulp.LpVariable(f"y_{i}_{j}_{k}", cat="Binary")
         for k in M for i in J0 for j in J
         if i != j and k in inst.E[j] and (i == 0 or k in inst.E[i])}

    C = {i: pulp.LpVariable(f"C_{i}", lowBound=0) for i in J}   # conclusao
    T = {i: pulp.LpVariable(f"T_{i}", lowBound=0) for i in J}   # atraso
    u = {i: pulp.LpVariable(f"u_{i}", lowBound=1, upBound=inst.n) for i in J}

    # ---- Funcao objetivo ---------------------------------------------
    obj = pulp.lpSum(inst.w[i] * T[i] for i in J)

    if penalidade_antecipacao:
        A = {i: pulp.LpVariable(f"A_{i}", lowBound=0) for i in J}
        for i in J:
            mod += A[i] >= inst.d[i] - C[i], f"antecipacao_{i}"
        obj += pulp.lpSum(penalidade_antecipacao.get(i, 0) * A[i] for i in J)

    mod += obj, "atraso_ponderado_total"

    # ---- (1) Alocacao unica em linha elegivel ------------------------
    for i in J:
        mod += pulp.lpSum(x[(i, k)] for k in inst.E[i]) == 1, f"alocacao_{i}"

    # ---- (2) Consistencia alocacao x sequencia -----------------------
    # cada item alocado tem exatamente um predecessor imediato
    for j in J:
        for k in inst.E[j]:
            mod += (pulp.lpSum(y[(i, j, k)] for i in J0
                               if (i, j, k) in y) == x[(j, k)],
                    f"predecessor_{j}_{k}")
    # e no maximo um sucessor imediato
    for i in J:
        for k in inst.E[i]:
            mod += (pulp.lpSum(y[(i, j, k)] for j in J
                               if (i, j, k) in y) <= x[(i, k)],
                    f"sucessor_{i}_{k}")

    # ---- (3) Cada linha inicia no maximo uma sequencia ---------------
    for k in M:
        mod += (pulp.lpSum(y[(0, j, k)] for j in J if (0, j, k) in y) <= 1,
                f"inicio_linha_{k}")

    # ---- (4) Tempos de conclusao (disjuntivas big-M) -----------------
    for (i, j, k) in y:
        if i == 0:
            mod += (C[j] >= inst.s[(0, j)] + inst.p[(j, k)] - V * (1 - y[(i, j, k)]),
                    f"tempo_ini_{j}_{k}")
        else:
            mod += (C[j] >= C[i] + inst.s[(i, j)] + inst.p[(j, k)]
                    - V * (1 - y[(i, j, k)]),
                    f"tempo_{i}_{j}_{k}")

    # ---- (5) Definicao do atraso -------------------------------------
    for i in J:
        mod += T[i] >= C[i] - inst.d[i], f"atraso_{i}"

    # ---- (6) Eliminacao de subciclos (MTZ) ---------------------------
    if mtz:
        for (i, j, k) in y:
            if i != 0:
                mod += (u[i] - u[j] + inst.n * y[(i, j, k)] <= inst.n - 1,
                        f"mtz_{i}_{j}_{k}")

    return mod, {"x": x, "y": y, "C": C, "T": T, "u": u}


# ----------------------------------------------------------------------
# 3. RESOLUCAO E LEITURA DA SOLUCAO
# ----------------------------------------------------------------------

def resolver(inst: Instancia, tempo_limite=300, msg=False, **kwargs):
    mod, var = construir_modelo(inst, **kwargs)
    solver = pulp.PULP_CBC_CMD(msg=msg, timeLimit=tempo_limite)
    mod.solve(solver)
    return mod, var


def extrair_sequencias(inst: Instancia, var):
    """Reconstroi, para cada linha, a sequencia de itens a partir de y."""
    y = var["y"]
    seq = {k: [] for k in inst.M}
    for k in inst.M:
        prox = {i: j for (i, j, kk) in y
                if kk == k and y[(i, j, kk)].value() is not None
                and y[(i, j, kk)].value() > 0.5}
        atual = prox.get(0)
        while atual is not None:
            seq[k].append(atual)
            atual = prox.get(atual)
    return seq


def relatorio(inst: Instancia, mod, var):
    seq = extrair_sequencias(inst, var)
    C, T = var["C"], var["T"]

    print(f"Status: {pulp.LpStatus[mod.status]}")
    print(f"Atraso ponderado total (Z): {pulp.value(mod.objective):.2f}\n")

    for k in inst.M:
        if not seq[k]:
            print(f"Linha {k}: ociosa")
            continue
        print(f"Linha {k}: " + " -> ".join(
            inst.nomes.get(i, f"J{i}") for i in seq[k]))
        anterior, t = 0, 0.0
        for i in seq[k]:
            setup = inst.s[(anterior, i)]
            ini = t + setup
            fim = ini + inst.p[(i, k)]
            marca = "ATRASO" if fim > inst.d[i] + 1e-6 else "ok"
            print(f"   {inst.nomes.get(i, f'J{i}'):<8} setup={setup:>5.1f} "
                  f"[{ini:>6.1f} - {fim:>6.1f}]  d={inst.d[i]:>6.1f} "
                  f"w={inst.w[i]:>4.1f}  T={max(0, fim - inst.d[i]):>6.1f}  {marca}")
            anterior, t = i, fim
        print()

    total = sum(inst.w[i] * (T[i].value() or 0) for i in inst.J)
    print(f"Conferencia sum(w_i*T_i) = {total:.2f}")
    return seq


# ----------------------------------------------------------------------
# 4. INSTANCIA DE TESTE (inventada, escala reduzida)
# ----------------------------------------------------------------------

def instancia_pequena():
    """
    6 itens, 3 linhas. Itens 1 e 2 tem cabo de aco -> so a linha 3
    (analoga a Linha 4 da fabrica) os aceita.
    Setups assimetricos: montar o dispositivo de cabo custa mais que
    desmonta-lo.
    """
    n, m = 6, 3
    cabo = {1, 2}
    nomes = {i: (f"CA{i}" if i in cabo else f"TX{i}") for i in range(1, n + 1)}

    E = {i: ([3] if i in cabo else [1, 2, 3]) for i in range(1, n + 1)}

    # linhas com velocidades diferentes: linha 1 rapida, linha 3 lenta
    base = {1: 20, 2: 24, 3: 14, 4: 18, 5: 22, 6: 16}
    fator = {1: 1.0, 2: 1.2, 3: 1.4}
    p = {(i, k): base[i] * fator[k] for i in range(1, n + 1) for k in E[i]}

    # setup: 4 se troca dentro da mesma familia; 12 para montar cabo;
    # 7 para desmontar cabo (assimetria)
    def setup(i, j):
        if i == 0:
            return 6.0
        if (i in cabo) == (j in cabo):
            return 4.0
        return 12.0 if j in cabo else 7.0

    s = {(i, j): setup(i, j) for i in range(0, n + 1)
         for j in range(1, n + 1) if i != j}

    d = {1: 30, 2: 45, 3: 25, 4: 40, 5: 30, 6: 38}
    w = {1: 5, 2: 1, 3: 3, 4: 1, 5: 4, 6: 2}

    return Instancia(n=n, m=m, p=p, s=s, d=d, w=w, E=E, nomes=nomes)


# ----------------------------------------------------------------------
# 5. VALIDACAO POR ENUMERACAO EXAUSTIVA (instancias muito pequenas)
# ----------------------------------------------------------------------

def forca_bruta(inst: Instancia):
    """
    Enumera todas as atribuicoes item->linha e todas as sequencias
    dentro de cada linha. Uso apenas para n <= 6, como conferencia
    independente do resultado do solver.
    """
    from itertools import permutations, product

    melhor, melhor_plano = float("inf"), None
    atribuicoes = product(*[inst.E[i] for i in inst.J])

    for atrib in atribuicoes:
        aloc = {k: [i for i, kk in zip(inst.J, atrib) if kk == k] for k in inst.M}
        opcoes = []
        for k in inst.M:
            perms = list(permutations(aloc[k])) or [()]
            opcoes.append([(k, seq) for seq in perms])
        for combo in product(*opcoes):
            z = 0.0
            for k, seq in combo:
                anterior, t = 0, 0.0
                for i in seq:
                    t += inst.s[(anterior, i)] + inst.p[(i, k)]
                    z += inst.w[i] * max(0.0, t - inst.d[i])
                    anterior = i
            if z < melhor - 1e-9:
                melhor, melhor_plano = z, combo
    return melhor, melhor_plano


if __name__ == "__main__":
    inst = instancia_pequena()

    print("=" * 62)
    print("MODELO PLI")
    print("=" * 62)
    mod, var = resolver(inst)
    relatorio(inst, mod, var)

    print("\n" + "=" * 62)
    print("VALIDACAO POR ENUMERACAO EXAUSTIVA")
    print("=" * 62)
    z_bf, plano = forca_bruta(inst)
    print(f"Otimo por forca bruta: {z_bf:.2f}")
    print(f"Otimo pelo solver:     {pulp.value(mod.objective):.2f}")
    print("CONFEREM" if abs(z_bf - pulp.value(mod.objective)) < 1e-4
          else "DIVERGENCIA - revisar formulacao")