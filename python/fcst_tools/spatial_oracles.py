# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent closed-form preparation for WP-16, never calls production physics."""
import math


def steady_rod(x, left=300., right=320., length=1., conductivity=2., area=.5):
    return {"temperature_K": left+(right-left)*x/length,
            "flux_W_m2": -conductivity*(right-left)/length,
            "power_W": -conductivity*(right-left)*area/length}


def transient_mode(x, t, alpha=.1):
    return 300+math.exp(-math.pi**2*alpha*t)*math.sin(math.pi*x)


def rotated_flux(conductivity, gradient, rotation):
    local = [-sum(k*g for k,g in zip(row,gradient)) for row in conductivity]
    return [sum(r*q for r,q in zip(row,local)) for row in rotation]


def boundary_power(flux, outward_normal, area):
    return sum(q*n for q,n in zip(flux,outward_normal))*area
