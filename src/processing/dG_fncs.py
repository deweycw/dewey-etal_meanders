import numpy as np

def calc_fh_dG(data, time_t):
    # Rxn:    1.00 Ac- + 8.00 FHY + 15.00 H+ = 8.00 Fe++ + 2.00 HCO3- + 20.00 H2O 
    dG0 =   -612.0 #kJ per mol Ac- 

    fe2 = np.power(data['Free_Fe++ [M]'][time_t],8)
    hco3 = np.power(data['Free_HCO3- [M]'][time_t],2)
    proton = np.power(np.power(10, -1*data['pH'][time_t]),15)
    ac = np.power(data['Free_Ac- [M]'][time_t],1)

    num =  np.multiply(fe2,hco3)
    den = np.multiply(proton,ac)

    q = np.divide(num,den)
    #print(np.log(q))

    R = 8.314e-3 # kJ / (K * mol)
    dGr = dG0 + R*273.15*np.log(q)

    return dGr


def calc_gt_dG(data, time_t):
    # Rxn:    1.00 Ac- + 8.00 FHY + 15.00 H+ = 8.00 Fe++ + 2.00 HCO3- + 12.00 H2O 
    dG0 =   -464 #kJ per mol Ac-

    fe2 = np.power(data['Free_Fe++ [M]'][time_t],8)
    hco3 = np.power(data['Free_HCO3- [M]'][time_t],2)
    proton = np.power(np.power(10, -1*data['pH'][time_t]),15)
    ac = np.power(data['Free_Ac- [M]'][time_t],1)

    num =  np.multiply(fe2,hco3)
    den = np.multiply(proton,ac)

    q = np.divide(num,den)

    #print(np.log(q))
    R = 8.314e-3 # kJ / (K * mol)
    dGr = dG0 + R*273.15*np.log(q)

    return dGr


def calc_sulf_dG(data, time_t):
    # Rxn:    1.00 Ac- + 1.00 SO4-- = 1.00 HS- + 2.00 HCO3- 
    dG0 =   -48.1 # kJ per mol Ac-, Kocar & Fendorf 2009

    sulfate = np.power((data['Free_SO4-- [M]'][time_t]*data['Gamma_SO4--'][time_t]),1)
    hco3 = np.power((data['Free_HCO3- [M]'][time_t]*data['Gamma_HCO3-'][time_t]),2)
    ac = np.power((data['Free_Ac- [M]'][time_t]*data['Gamma_Ac-'][time_t]),1)
    hs = np.power((data['Free_HS- [M]'][time_t]*data['Gamma_HS-'][time_t]),1)

    num =  np.multiply(hs,hco3)
    den = np.multiply(sulfate,ac)

    q = np.divide(num,den)

    #print(np.log(q))
    R = 8.314e-3 # kJ / (K * mol)
    dGr = dG0 + R*298.15*np.log(q)

    return dGr


def calc_FT(dgr, m, chi):
    return (1 - np.exp((dgr + m*50) / (chi * 8.314e-3 * 273.15 )))