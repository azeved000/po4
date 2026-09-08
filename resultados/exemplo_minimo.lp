\* RubberTech_atraso_ponderado *\
Minimize
atraso_ponderado_total: 8 T_CA1 + 5 T_TX1 + 2 T_TX2
Subject To
alocacao_CA1: x_CA1_L2 = 1
alocacao_TX1: x_TX1_L1 + x_TX1_L2 = 1
alocacao_TX2: x_TX2_L1 + x_TX2_L2 = 1
antecipacao_CA1: A_CA1 + C_CA1 >= 40
antecipacao_TX1: A_TX1 + C_TX1 >= 30
antecipacao_TX2: A_TX2 + C_TX2 >= 25
atraso_CA1: - C_CA1 + T_CA1 >= -40
atraso_TX1: - C_TX1 + T_TX1 >= -30
atraso_TX2: - C_TX2 + T_TX2 >= -25
entrada_CA1_L2: - x_CA1_L2 + y_INI_CA1_L2 + y_TX1_CA1_L2 + y_TX2_CA1_L2 = 0
entrada_TX1_L1: - x_TX1_L1 + y_INI_TX1_L1 + y_TX2_TX1_L1 = 0
entrada_TX1_L2: - x_TX1_L2 + y_CA1_TX1_L2 + y_INI_TX1_L2 + y_TX2_TX1_L2 = 0
entrada_TX2_L1: - x_TX2_L1 + y_INI_TX2_L1 + y_TX1_TX2_L1 = 0
entrada_TX2_L2: - x_TX2_L2 + y_CA1_TX2_L2 + y_INI_TX2_L2 + y_TX1_TX2_L2 = 0
mtz_CA1_TX1_L2: u_CA1 - u_TX1 + 3 y_CA1_TX1_L2 <= 2
mtz_CA1_TX2_L2: u_CA1 - u_TX2 + 3 y_CA1_TX2_L2 <= 2
mtz_TX1_CA1_L2: - u_CA1 + u_TX1 + 3 y_TX1_CA1_L2 <= 2
mtz_TX1_TX2_L1: u_TX1 - u_TX2 + 3 y_TX1_TX2_L1 <= 2
mtz_TX1_TX2_L2: u_TX1 - u_TX2 + 3 y_TX1_TX2_L2 <= 2
mtz_TX2_CA1_L2: - u_CA1 + u_TX2 + 3 y_TX2_CA1_L2 <= 2
mtz_TX2_TX1_L1: - u_TX1 + u_TX2 + 3 y_TX2_TX1_L1 <= 2
mtz_TX2_TX1_L2: - u_TX1 + u_TX2 + 3 y_TX2_TX1_L2 <= 2
origem_L1: y_INI_TX1_L1 + y_INI_TX2_L1 <= 1
origem_L2: y_INI_CA1_L2 + y_INI_TX1_L2 + y_INI_TX2_L2 <= 1
saida_CA1_L2: - x_CA1_L2 + y_CA1_TX1_L2 + y_CA1_TX2_L2 <= 0
saida_TX1_L1: - x_TX1_L1 + y_TX1_TX2_L1 <= 0
saida_TX1_L2: - x_TX1_L2 + y_TX1_CA1_L2 + y_TX1_TX2_L2 <= 0
saida_TX2_L1: - x_TX2_L1 + y_TX2_TX1_L1 <= 0
saida_TX2_L2: - x_TX2_L2 + y_TX2_CA1_L2 + y_TX2_TX1_L2 <= 0
tempo_CA1_TX1_L2: - C_CA1 + C_TX1 - 154 y_CA1_TX1_L2 >= -119
tempo_CA1_TX2_L2: - C_CA1 + C_TX2 - 154 y_CA1_TX2_L2 >= -125
tempo_TX1_CA1_L2: C_CA1 - C_TX1 - 154 y_TX1_CA1_L2 >= -104
tempo_TX1_TX2_L1: - C_TX1 + C_TX2 - 154 y_TX1_TX2_L1 >= -134
tempo_TX1_TX2_L2: - C_TX1 + C_TX2 - 154 y_TX1_TX2_L2 >= -131
tempo_TX2_CA1_L2: C_CA1 - C_TX2 - 154 y_TX2_CA1_L2 >= -104
tempo_TX2_TX1_L1: C_TX1 - C_TX2 - 154 y_TX2_TX1_L1 >= -129
tempo_TX2_TX1_L2: C_TX1 - C_TX2 - 154 y_TX2_TX1_L2 >= -125
tempo_inicial_CA1_L2: C_CA1 - 154 y_INI_CA1_L2 >= -112
tempo_inicial_TX1_L1: C_TX1 - 154 y_INI_TX1_L1 >= -126
tempo_inicial_TX1_L2: C_TX1 - 154 y_INI_TX1_L2 >= -122
tempo_inicial_TX2_L1: C_TX2 - 154 y_INI_TX2_L1 >= -131
tempo_inicial_TX2_L2: C_TX2 - 154 y_INI_TX2_L2 >= -128
Bounds
 1 <= u_CA1 <= 3
 1 <= u_TX1 <= 3
 1 <= u_TX2 <= 3
Binaries
x_CA1_L2
x_TX1_L1
x_TX1_L2
x_TX2_L1
x_TX2_L2
y_CA1_TX1_L2
y_CA1_TX2_L2
y_INI_CA1_L2
y_INI_TX1_L1
y_INI_TX1_L2
y_INI_TX2_L1
y_INI_TX2_L2
y_TX1_CA1_L2
y_TX1_TX2_L1
y_TX1_TX2_L2
y_TX2_CA1_L2
y_TX2_TX1_L1
y_TX2_TX1_L2
End
