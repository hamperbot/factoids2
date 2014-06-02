import parsley

_grammar = r"""
parse = pair:head (' '+ pair)*:tail -> dict([head] + tail)
pair = ident:i '=' value:v -> (i, v)
ident = <letter letterOrDigit*>
value = string | regex | number | word

string = '"' (escapedChar | ~'"' anything)*:c '"' -> ''.join(c)
       | "'" (escapedChar | ~"'" anything)*:c "'" -> ''.join(c)
regex = '/' (escapedChar | ~'/' anything)*:c '/' -> '/' + ''.join(c) + '/'
word = <(~' ' anything)+>

# A number is optionally a negative sign, followed by an intPart, and then
# maybe a floatPart.
number = ('-' | -> ''):sign
         ( (intPart:i floatPart:f -> float(sign + i + f ))
         | (intPart:i -> int(sign + i))
         | (floatPart:f -> float(sign + '0' + f)))

digit = :x ?(x in '0123456789') -> x
digit1_9 = :x ?(x in '123456789') -> x

intPart = (digit1_9:first <digit+>:rest -> first + rest)
        | digit
floatPart = <'.' digit+>

# This matches a *single* backslash, followed by something else, which it returns.
escapedChar = "\\\\" anything
"""

learn_grammar = parsley.makeGrammar(_grammar, {})
