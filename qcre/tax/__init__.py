"""Quebec / Canada real-estate tax engine.

Every rate, threshold and bracket lives in a dated, sourced rate book
(:mod:`qcre.tax.rates`). The calculators in this package read from a ``RateBook`` for a
given taxation year so results never silently go stale and every figure is auditable.

Calculators:
    sales_tax     GST/QST, taxable/exempt supplies, ITC/ITR apportionment, net remittance
    cca           Capital cost allowance pools (Class 1/8/10/13/50), AII phase-out, recapture
    capital       Capital gains (50% inclusion), CDA, ACB
    corporate     CCPC tax: SBD vs general vs investment income, SIB test, RDTOH, dividend refund
    transfer_duty Droits de mutation immobilière (welcome tax), Montreal brackets, exemptions
    trust         21-year deemed disposition, beneficiary allocation, TOSI screening
    personal      Federal + Quebec personal tax, dividend integration
    optimization  Salary-vs-dividend, distribute-vs-retain, CCA timing, advisory flags
"""
