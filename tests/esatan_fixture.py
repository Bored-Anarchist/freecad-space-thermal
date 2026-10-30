# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned synthetic ESATAN inputs; no acquired model values or metadata."""
from fcst_exchange.esatan import EsatanUnits

UNITS = EsatanUnits('degC','J/K','W/K','W','s')
NETWORK = (b'# Owned constant network\r\n$MODEL MAIN\r\n$LOCALS\r\n$REAL\r\n'
           b'BASE=2D0; SCALE=BASE/2;\r\n$NODES\r\n'
           b"D1 = 'first; node', T=20, C=100*SCALE;\r\n"
           b"B2 = 'boundary', T=30, C=0;\r\n$CONDUCTORS\r\n"
           b'GL(1,2)=BASE;\r\n$INITIAL\r\nQI1=5;\r\n$ENDMODEL\r\n')
REAL_ATTRIBUTES = ('Temperature','Capacitance','Total_Albedo_Heat_Source','Total_Earth_Heat_Source',
    'Total_Internal_Heat_Source','Total_Rest_Heat_Source','Total_Solar_Heat_Source','Area',
    'Solar_Absorptivity','Infra-Red_Emissivity','Incident_Albedo_Heat_Source',
    'Incident_Earth_Heat_Source','Incident_Solar_Heat_Source','X_Coordinate','Y_Coordinate','Z_Coordinate')


def tmd(path):
    import h5py
    import numpy as np
    with h5py.File(path,'w') as f:
        a=f.create_group('AnalysisSet1'); a.attrs['Description']=np.array([b'CASE']); a.attrs['TAbs']=273.15
        dtype=np.dtype([('modelName','S24'),('parentId','<i4'),('modelPath','S64')])
        a.create_dataset('models',data=np.array([(b'MAIN',0,b'/MAIN')],dtype=dtype))
        a.create_dataset('thermalNodes',data=np.array([[1,1],[2,1]],dtype='<i4'))
        a.create_dataset('thermalNodesRealAttributes',data=np.array(REAL_ATTRIBUTES,dtype='S32'))
        a.create_dataset('thermalNodesStringAttributes',data=np.array([b'Type',b'Label'],dtype='S32'))
        d=a.create_group('DataGroup1'); d.attrs['ESATAN_version']=np.array([b'2025'])
        d.create_dataset('times',data=np.array([0.,10.,20.]))
        values=np.zeros((3,2,16)); values[:,:,0]=[[20,30],[21,30],[23,30]]; values[:,:,4]=[[5,0],[5,0],[8,0]]
        d.create_dataset('thermalNodesRealData',data=values)
        types=np.array([[[b'D',b'first'],[b'B',b'boundary']]]*3,dtype='S24')
        d.create_dataset('thermalNodesStringData',data=types)
    return path.read_bytes()
